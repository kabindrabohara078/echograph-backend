from datetime import datetime
import json
from embedding import generate_embedding
from database import conn
from model.graph import (
    extract_entities,
    traverse_linked_memories,
    reinforce_links
)

def memory_cleanup(cursor, user_id: int):
    """
    Purges expired non-permanent nodes and soft-deleted nodes for the user.
    Uses real-time timestamps and elapsed time. Permanent nodes are never purged.
    """
    now_dt = datetime.utcnow()
    cursor.execute(
        """
        SELECT ref_id, node_life, initial_date, expires_at
        FROM memories_v2
        WHERE user_id = %s
          AND state != 'permanent'
          AND node_life IS NOT NULL
        """,
        (user_id,)
    )
    candidates = cursor.fetchall()
    expired_ids = []

    for ref_id, node_life, init_date, exp_at in candidates:
        if exp_at:
            try:
                exp_dt = exp_at if isinstance(exp_at, datetime) else datetime.fromisoformat(str(exp_at))
                if now_dt >= exp_dt:
                    expired_ids.append(ref_id)
                    continue
            except Exception:
                pass

        if init_date and node_life is not None:
            try:
                init_dt = init_date if isinstance(init_date, datetime) else datetime.fromisoformat(str(init_date))
                elapsed_hours = (now_dt - init_dt).total_seconds() / 3600
                if node_life <= 0 or elapsed_hours >= node_life:
                    expired_ids.append(ref_id)
                    continue
            except Exception:
                pass

        if node_life is not None and node_life <= 0:
            expired_ids.append(ref_id)

    if expired_ids:
        cursor.execute(
            """
            DELETE FROM memories_v2
            WHERE ref_id = ANY(%s)
            """,
            (expired_ids,)
        )
        conn.commit()
        print(f"Cleaned up {len(expired_ids)} expired memory nodes for user #{user_id}")

    # Also clean soft-deleted
    cursor.execute(
        """
        DELETE FROM memories_v2
        WHERE user_id = %s AND (type = 'delete' OR state IN ('deleted', 'expired'))
        """,
        (user_id,)
    )
    conn.commit()


def search_nodes(cursor, user_id: int, vector_str: str, category_type: str = None, limit: int = None):
    """
    Retrieves active, permanent & temporary facts using pgvector cosine distance + adaptive decay ranking.
    Excludes deleted or expired memories.
    Does not artificially cap at 5 or 10: fetches all relevant candidates up to limit (default 100).
    """
    query = """
        SELECT
            ref_id,
            content,
            type,
            importance_score,
            access_ratio,
            initial_date,

            embedding <=> %s::vector AS distance,

            (
                (
                    1.0 / (1.0 + (embedding <=> %s::vector))
                )
                + (0.25 * importance_score)
                + (0.1 * LN(1 + access_ratio))
                + (
                    0.2 * EXP(
                        -0.000001 * EXTRACT(EPOCH FROM (NOW() - initial_date))
                    )
                )
            ) AS final_rank,
            state,
            node_life,
            expires_at,
            linkable,
            ref_link,
            entities

        FROM memories_v2
        WHERE
            user_id = %s
            AND type != 'delete'
            AND state NOT IN ('deleted', 'expired')
            AND (state = 'permanent' OR node_life IS NULL OR node_life > 0)
    """
    params = [vector_str, vector_str, user_id]

    if category_type and category_type.strip() and category_type.strip().lower() != "all":
        query += " AND LOWER(type) = LOWER(%s)"
        params.append(category_type.strip().lower())

    query += " ORDER BY final_rank DESC"
    if limit is not None and limit > 0:
        query += f" LIMIT {int(limit)}"
    else:
        query += " LIMIT 100"  # Broad pool so no relevant memories are missed

    cursor.execute(query, tuple(params))
    results = cursor.fetchall()

    print(f"\n=========== RAG VECTOR SEARCH RESULTS (User #{user_id}) ===========")
    if not results:
        print("No matching memory nodes found")
        return []
    for row in results:
        life_str = "Permanent" if (row[8] == 'permanent' or row[9] is None or row[9] == -1) else f"{row[9]}h remaining"
        print(f"Node #{row[0]} | Type: {row[2]} | Dist: {row[6]:.3f} | Rank: {row[7]:.3f} | Life: {life_str} | Linkable: {row[11]} | Content: '{row[1]}'")
    print("===================================================================\n")

    return results


def retrieve_context(current_user, search):
    """
    Primary memory retrieval engine with Knowledge Graph dynamic expansion:
    1. Vector similarity search retrieves candidate seed nodes.
    2. Entity-based exact matching adds any memories explicitly tagged with query entities.
    3. If linkable=True and similarity score is high, recursively/iteratively fetches
       all connected graph nodes until all linkables are retrieved.
    4. Presents ALL relevant memories in descending order without artificial truncation.
    5. Reinforces connections between co-retrieved nodes.
    """
    user_id = int(current_user)
    query_text = search.query.strip()
    query_embedding = generate_embedding(query_text)
    vector_str = f"[{','.join(map(str, query_embedding))}]"

    cursor = conn.cursor()

    # Step 1: Clean up any expired or deleted nodes first
    memory_cleanup(cursor, user_id)

    # Step 2: Search active/temporary facts with category filter if specified
    category_filter = getattr(search, 'type', None)
    req_limit = getattr(search, 'limit', None)
    req_threshold = getattr(search, 'threshold', None)
    max_dist = float(req_threshold) if req_threshold is not None else 0.85

    db_response = search_nodes(cursor, user_id, vector_str, category_type=category_filter, limit=req_limit)

    # Filter by relevance threshold
    matching_rows = [row for row in db_response if row[6] <= max_dist]
    matched_ids = {row[0] for row in matching_rows}

    # Step 3: Entity-based fallback / augmentation
    # If the user asks about specific entities (e.g. "Tell me about my friend amar"),
    # ensure memories tagged with "amar" are included even if vector distance is slightly higher.
    query_entities = extract_entities(query_text)
    specific_entities = [
        e for e in query_entities
        if e not in {"friend", "mother", "father", "brother", "sister", "college", "school", "company", "project"}
    ]

    for ent in specific_entities:
        cursor.execute(
            """
            SELECT
                ref_id, content, type, importance_score, access_ratio, initial_date,
                embedding <=> %s::vector AS distance,
                (
                    (1.0 / (1.0 + (embedding <=> %s::vector)))
                    + (0.25 * importance_score)
                    + (0.1 * LN(1 + access_ratio))
                    + (0.2 * EXP(-0.000001 * EXTRACT(EPOCH FROM (NOW() - initial_date))))
                ) AS final_rank,
                state, node_life, expires_at, linkable, ref_link, entities
            FROM memories_v2
            WHERE user_id = %s
              AND type != 'delete'
              AND state NOT IN ('deleted', 'expired')
              AND (state = 'permanent' OR node_life IS NULL OR node_life > 0)
              AND (
                  entities LIKE %s
                  OR LOWER(content) LIKE %s
              )
            ORDER BY final_rank DESC
            LIMIT 10
            """,
            (vector_str, vector_str, user_id, f"%{ent}%", f"%{ent}%")
        )
        ent_rows = cursor.fetchall()
        for er in ent_rows:
            if er[0] not in matched_ids:
                matched_ids.add(er[0])
                matching_rows.append(er)

    if not matching_rows:
        conn.commit()
        return {
            "results": [],
            "count": 0,
            "message": f"No context matched relevance threshold (<= {max_dist})",
            "user_id": user_id
        }

    # Step 4: Assemble seed context nodes
    context_nodes = []
    for row in matching_rows:
        cand_entities = []
        if len(row) > 13 and row[13]:
            try:
                cand_entities = json.loads(row[13]) if isinstance(row[13], str) else row[13]
            except Exception:
                cand_entities = []

        context_nodes.append({
            "id": row[0],
            "content": row[1],
            "type": row[2],
            "importance_score": float(row[3]),
            "access_ratio": float(row[4]),
            "created_at": str(row[5]),
            "distance": float(row[6]),
            "final_rank": float(row[7]),
            "state": str(row[8]) if len(row) > 8 and row[8] else "active",
            "node_life": int(row[9]) if len(row) > 9 and row[9] is not None else -1,
            "expires_at": str(row[10]) if len(row) > 10 and row[10] else None,
            "linkable": bool(row[11]) if len(row) > 11 else True,
            "ref_link": row[12] if len(row) > 12 else None,
            "entities": cand_entities,
            "linked_memories": []
        })

    # Step 5: Knowledge Graph Traversal
    # "check if the linkable is true and if the fetched score is high then you just keep on fetching rows until there are linkables right?"
    # Score threshold is 0.50 (or max_dist <= 0.85). If true, traverse recursively/iteratively along all linkable edges.
    linked_map = traverse_linked_memories(
        cursor=cursor,
        user_id=user_id,
        seed_nodes=context_nodes,
        score_threshold=0.50,
        max_depth=5,
        max_total_linked=50
    )

    # Attach linked nodes to their respective seeds, and collect all newly discovered linked nodes
    existing_node_ids = {node["id"] for node in context_nodes}
    newly_discovered_nodes = []

    for node in context_nodes:
        node_id = node["id"]
        links = linked_map.get(node_id, [])
        node["linked_memories"] = links

        for linked_item in links:
            lid = linked_item["id"]
            if lid not in existing_node_ids:
                existing_node_ids.add(lid)
                # Compute estimated rank based on parent rank & relation weight
                parent_rank = node["final_rank"]
                edge_weight = linked_item.get("graph_weight", 1.0)
                synthesized_rank = round(parent_rank * 0.95 * min(1.0, edge_weight), 3)

                newly_discovered_nodes.append({
                    "id": lid,
                    "content": linked_item["content"],
                    "type": linked_item["type"],
                    "importance_score": linked_item["importance_score"],
                    "access_ratio": linked_item["access_ratio"],
                    "created_at": linked_item["created_at"],
                    "distance": round(node["distance"] + 0.05, 3),
                    "final_rank": synthesized_rank,
                    "state": linked_item["state"],
                    "node_life": linked_item["node_life"],
                    "expires_at": linked_item["expires_at"],
                    "linkable": linked_item.get("linkable", True),
                    "ref_link": linked_item.get("ref_link"),
                    "entities": [],
                    "linked_memories": [],
                    "is_graph_expanded": True,
                    "graph_relation": linked_item.get("relation"),
                    "linked_to_seed": node_id
                })

    # Combine all primary and graph-expanded nodes so all related memories are presented
    all_results = context_nodes + newly_discovered_nodes

    # Sort all results in descending order of relevance / final_rank
    all_results.sort(key=lambda x: x.get("final_rank", 0.0), reverse=True)

    # If the user specified a strict limit, apply it; otherwise show all matching rows in order
    if req_limit is not None and req_limit > 0:
        all_results = all_results[:req_limit]

    # Step 6: Increment access frequency & reinforce graph links
    all_ids = [n["id"] for n in all_results]
    if all_ids:
        cursor.execute(
            """
            UPDATE memories_v2
            SET
                access_ratio = access_ratio * 1.05,
                last_accessed = NOW()
            WHERE ref_id = ANY(%s)
            """,
            (all_ids,)
        )
        reinforce_links(cursor, all_ids, user_id)

    conn.commit()

    return {
        "results": all_results,
        "count": len(all_results),
        "user_id": user_id
    }
