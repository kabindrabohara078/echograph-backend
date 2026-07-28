from embedding import generate_embedding
from database import conn

def memory_cleanup(cursor, user_id: int):
    """
    Purges expired temporary nodes (node_life <= 0) and soft-deleted nodes for the user.
    """
    cursor.execute(
        """
        DELETE FROM memories_v2
        WHERE user_id = %s
        AND (node_life <= 0 OR type = 'delete' OR state = 'deleted')
        RETURNING ref_id, content
        """,
        (user_id,)
    )
    deleted_rows = cursor.fetchall()
    conn.commit()
    if deleted_rows:
        print(f"Cleaned up {len(deleted_rows)} expired/deleted memory nodes for user #{user_id}")

def search_nodes(cursor, user_id: int, vector_str: str, category_type: str = None):
    """
    Retrieves active & temporary facts using pgvector cosine distance + adaptive decay ranking.
    Excludes deleted or expired memories.
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
            ) AS final_rank

        FROM memories_v2
        WHERE
            user_id = %s
            AND type != 'delete'
            AND state NOT IN ('deleted', 'expired')
    """
    params = [vector_str, vector_str, user_id]

    if category_type and category_type.strip() and category_type != "All":
        query += " AND type = %s"
        params.append(category_type.strip())

    query += " ORDER BY final_rank DESC LIMIT 5"

    cursor.execute(query, tuple(params))
    results = cursor.fetchall()

    print(f"\n=========== RAG SEARCH RESULTS (User #{user_id}) ===========")
    if not results:
        print("No matching memory nodes found")
        return []
    for row in results:
        print(f"Node #{row[0]} | Type: {row[2]} | Dist: {row[6]:.3f} | Rank: {row[7]:.3f} | Content: '{row[1]}'")
    print("=========================================================\n")

    return results

def retrieve_context(current_user, search):
    user_id = int(current_user)
    query_embedding = generate_embedding(search.query)
    vector_str = f"[{','.join(map(str, query_embedding))}]"

    cursor = conn.cursor()

    # Step 1: Clean up any expired or deleted nodes first
    memory_cleanup(cursor, user_id)

    # Step 2: Search active/temporary facts with category filter if specified
    category_filter = getattr(search, 'type', None)
    db_response = search_nodes(cursor, user_id, vector_str, category_type=category_filter)

    if db_response:
        # Filter matching rows by reasonable distance threshold
        matching_rows = [row for row in db_response if row[6] < 0.85]
        if not matching_rows:
            matching_rows = db_response

        filtered_ids = [row[0] for row in matching_rows]

        # Step 3: Increment access frequency & update last_accessed timestamp
        cursor.execute(
            """
            UPDATE memories_v2
            SET
                access_ratio = access_ratio * 1.05,
                last_accessed = NOW()
            WHERE ref_id = ANY(%s)
            """,
            (filtered_ids,)
        )

        context_nodes = []
        for row in matching_rows:
            context_nodes.append({
                "id": row[0],
                "content": row[1],
                "type": row[2],
                "importance_score": float(row[3]),
                "access_ratio": float(row[4]),
                "created_at": str(row[5]),
                "distance": float(row[6]),
                "final_rank": float(row[7])
            })

        conn.commit()

        return {
            "results": context_nodes,
            "count": len(context_nodes),
            "user_id": user_id
        }
    else:
        conn.commit()
        return {
            "results": [],
            "message": "No context exists for the user"
        }
