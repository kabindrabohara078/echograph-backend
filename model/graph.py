"""
EchoGraph Dynamic Memory Knowledge Graph Engine
Handles entity extraction, dynamic link creation, transitive graph traversal, and Hebbian link reinforcement.
"""
import re
import json
import datetime
from collections import deque
from typing import List, Set, Dict, Any, Optional

# Core stop words to filter out noise from extracted entities
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "at", "from",
    "by", "for", "with", "about", "against", "between", "into", "through", "during",
    "before", "after", "above", "below", "to", "of", "in", "on", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "i",
    "you", "he", "she", "it", "we", "they", "my", "your", "his", "her", "its", "our",
    "their", "me", "him", "us", "them", "this", "that", "these", "those", "user",
    "users", "there", "here", "what", "which", "who", "whom", "will", "would", "can",
    "could", "should", "tell", "show", "give", "know", "think", "like", "just", "also"
}

RELATION_KEYWORDS = {
    "friend", "mother", "father", "brother", "sister", "wife", "husband", "son",
    "daughter", "colleague", "boss", "manager", "teacher", "mentor", "student",
    "company", "college", "university", "school", "office", "workplace", "city",
    "country", "database", "framework", "language", "project", "hobby", "sport",
    "major", "degree", "profession", "job", "role"
}


def extract_entities(text: str) -> List[str]:
    """
    Extracts key named entities, proper nouns, and relational concepts from text.
    Returns a deduplicated, sorted list of lowercase entity strings.
    """
    if not text or not text.strip():
        return []

    entities: Set[str] = set()

    # 1. Structural relationship & predicate patterns
    patterns = [
        # "friend name is amar", "mother's name is Janaki"
        r"(?:friend|mother|father|brother|sister|wife|husband|colleague|boss|manager|partner)(?:'s)?\s+(?:name\s+is\s+)?([A-Za-z0-9_-]+)",
        # "name is Amar", "called Amar"
        r"(?:name\s+is|named|called)\s+([A-Za-z0-9_-]+)",
        # "studies at Study World College", "works at Google"
        r"(?:studies\s+at|works\s+at|graduated\s+from|lives\s+in|majors\s+in)\s+([^,.\n;]+)",
        # "X studies at Y", "X works at Y"
        r"([A-Za-z0-9_-]+)\s+(?:studies\s+at|works\s+at|graduated\s+from|lives\s+in)\s+([^,.\n;]+)",
    ]

    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            for g in m.groups():
                if g:
                    cleaned = g.strip().strip("'\".,;:()[]{}").lower()
                    if cleaned and cleaned not in STOP_WORDS and len(cleaned) > 2:
                        entities.add(cleaned)

    # 2. Multi-word Title-Cased proper nouns (e.g. "Study World College", "Janaki Devi")
    cap_phrases = re.findall(r"\b[A-Z][a-zA-Z0-9_-]*(?:\s+[A-Z][a-zA-Z0-9_-]*)+\b", text)
    for phrase in cap_phrases:
        cleaned = phrase.strip().lower()
        if cleaned not in STOP_WORDS and len(cleaned) > 2:
            entities.add(cleaned)

    # 3. Standalone capitalized words (e.g. "Amar", "FastAPI", "React", "PostgreSQL", "Boston")
    cap_words = re.findall(r"\b[A-Z][a-zA-Z0-9_+#.-]*\b", text)
    for word in cap_words:
        cleaned = word.strip().lower()
        if cleaned not in STOP_WORDS and len(cleaned) > 2:
            entities.add(cleaned)

    # 4. Keyword and relation matching
    words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
    for w in words:
        if w in RELATION_KEYWORDS:
            entities.add(w)

    return sorted(list(entities))


def calculate_cosine_distance(v1, v2) -> float:
    """Calculates cosine distance between two float vectors (0.0 = identical, 2.0 = opposite)."""
    try:
        import math
        dot = sum(x * y for x, y in zip(v1, v2))
        na = math.sqrt(sum(x * x for x in v1))
        nb = math.sqrt(sum(x * x for x in v2))
        if na == 0 or nb == 0:
            return 1.0
        return max(0.0, 1.0 - (dot / (na * nb)))
    except Exception:
        return 1.0


def auto_link_memory(
    cursor,
    new_ref_id: int,
    user_id: int,
    content: str,
    embedding: Optional[List[float]] = None,
    linkable: bool = True
) -> List[Dict[str, Any]]:
    """
    Dynamically identifies potential memory connections for a newly created memory node:
    1. Extracts entities from content.
    2. Updates 'entities' column and ensures 'linkable = 1'.
    3. Finds candidate memories for this user where linkable = 1.
    4. Connects them via 'memory_links' (bidirectional edges) and 'ref_link' foreign key.
    Returns the list of created edges.
    """
    entities = extract_entities(content)
    entities_json = json.dumps(entities)

    if not linkable:
        cursor.execute(
            """
            UPDATE memories_v2
            SET entities = %s, linkable = 0
            WHERE ref_id = %s AND user_id = %s
            """,
            (entities_json, new_ref_id, user_id)
        )
        return []

    # Update new node's entities and ensure linkable = 1
    cursor.execute(
        """
        UPDATE memories_v2
        SET entities = %s, linkable = 1
        WHERE ref_id = %s AND user_id = %s
        """,
        (entities_json, new_ref_id, user_id)
    )

    created_links: List[Dict[str, Any]] = []
    if not entities and not embedding:
        return created_links

    # Fetch active candidates for this user to inspect potential links
    cursor.execute(
        """
        SELECT ref_id, content, entities, ref_link, embedding
        FROM memories_v2
        WHERE user_id = %s
          AND ref_id != %s
          AND state NOT IN ('deleted', 'expired')
          AND linkable = 1
        """,
        (user_id, new_ref_id)
    )
    candidates = cursor.fetchall()
    if not candidates:
        return created_links

    new_entities_set = set(entities)
    earliest_ref_link: Optional[int] = None

    for cand_id, cand_content, cand_entities_raw, cand_ref_link, cand_emb_raw in candidates:
        cand_entities = []
        if cand_entities_raw:
            try:
                cand_entities = json.loads(cand_entities_raw) if isinstance(cand_entities_raw, str) else cand_entities_raw
            except Exception:
                cand_entities = []

        # If candidate has no cached entities, extract dynamically
        if not cand_entities and cand_content:
            cand_entities = extract_entities(cand_content)

        cand_set = set(cand_entities)
        shared_entities = new_entities_set & cand_set

        # Filter out purely generic relation keywords if no proper noun entity is shared
        meaningful_shared = [
            e for e in shared_entities
            if e not in {"friend", "mother", "father", "brother", "sister", "college", "school", "company"}
        ]
        # If there's an entity overlap (like "amar", "fastapi", "reactjs")
        matched = False
        relation_label = ""
        weight = 1.0

        if meaningful_shared:
            matched = True
            relation_label = f"entity:{','.join(sorted(meaningful_shared))}"
            weight = 1.0 + (0.2 * len(meaningful_shared))
        elif shared_entities:
            # Check content directly: does cand_content mention any of new_entities, or vice versa?
            for ent in new_entities_set:
                if len(ent) > 2 and re.search(r"\b" + re.escape(ent) + r"\b", cand_content, re.IGNORECASE):
                    matched = True
                    relation_label = f"entity:{ent}"
                    weight = 1.0
                    break

        # Check semantic similarity if embedding is available
        if not matched and embedding is not None and cand_emb_raw is not None:
            try:
                cand_emb = json.loads(cand_emb_raw) if isinstance(cand_emb_raw, str) else cand_emb_raw
                dist = calculate_cosine_distance(embedding, cand_emb)
                if dist < 0.35:  # High semantic closeness
                    matched = True
                    relation_label = "semantic_affinity"
                    weight = max(0.5, 1.0 - dist)
            except Exception:
                pass

        if matched:
            # 1. Insert edge in both directions into memory_links
            for src, tgt in [(new_ref_id, cand_id), (cand_id, new_ref_id)]:
                try:
                    cursor.execute(
                        """
                        INSERT INTO memory_links (user_id, source_id, target_id, relation_type, weight)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (user_id, src, tgt, relation_label, weight)
                    )
                except Exception:
                    # Ignore duplicate edge if already exists
                    pass

            if earliest_ref_link is None or cand_id < earliest_ref_link:
                earliest_ref_link = cand_id

            created_links.append({
                "target_id": cand_id,
                "content": cand_content,
                "relation": relation_label,
                "weight": weight
            })

    # If links were formed and new node has no ref_link, set ref_link to primary parent node
    if earliest_ref_link is not None:
        cursor.execute(
            """
            UPDATE memories_v2
            SET ref_link = %s
            WHERE ref_id = %s AND user_id = %s AND ref_link IS NULL
            """,
            (earliest_ref_link, new_ref_id, user_id)
        )

    return created_links


def traverse_linked_memories(
    cursor,
    user_id: int,
    seed_nodes: List[Dict[str, Any]],
    score_threshold: float = 0.50,
    max_depth: int = 5,
    max_total_linked: int = 25
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Recursively/iteratively fetches connected graph nodes for high-scoring linkable memories:
    'when you fetch contexts, you check if the linkable is true and if the fetched score is high
    then you just keep on fetching rows until there are linkables right?'

    Returns a mapping: seed_ref_id -> list of connected memory node dicts.
    """
    linked_results: Dict[int, List[Dict[str, Any]]] = {}
    if not seed_nodes:
        return linked_results

    # Global set of node IDs already included in primary results to avoid redundant fetching
    visited_ids: Set[int] = {s["id"] for s in seed_nodes if "id" in s}
    total_fetched = 0

    now_dt = datetime.datetime.utcnow()

    for seed in seed_nodes:
        seed_id = seed.get("id")
        seed_linkable = seed.get("linkable", True)
        seed_score = seed.get("final_rank")
        seed_dist = seed.get("distance")

        # Determine if score is high enough to trigger graph traversal
        is_high_score = False
        if seed_score is not None and seed_score >= score_threshold:
            is_high_score = True
        elif seed_dist is not None and seed_dist <= 0.85:
            is_high_score = True
        elif seed_score is None and seed_dist is None:
            is_high_score = True  # Default to true if unranked

        if not seed_linkable or not is_high_score:
            linked_results[seed_id] = []
            continue

        # Queue for Breadth-First-Search traversal along linkable edges
        queue = deque([(seed_id, 0)])  # (current_node_id, depth)
        seed_connected: List[Dict[str, Any]] = []

        while queue and total_fetched < max_total_linked:
            curr_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # 1. Fetch connected neighbor IDs via memory_links table
            cursor.execute(
                """
                SELECT target_id, relation_type, weight
                FROM memory_links
                WHERE source_id = %s AND user_id = %s
                ORDER BY weight DESC
                """,
                (curr_id, user_id)
            )
            link_rows = cursor.fetchall()

            # 2. Also fetch connected nodes via ref_link foreign key (parent and children)
            cursor.execute(
                """
                SELECT ref_id, 'ref_link:parent', 1.0
                FROM memories_v2
                WHERE ref_id = (SELECT ref_link FROM memories_v2 WHERE ref_id = %s AND user_id = %s)
                  AND user_id = %s
                UNION
                SELECT ref_id, 'ref_link:child', 1.0
                FROM memories_v2
                WHERE ref_link = %s AND user_id = %s
                """,
                (curr_id, user_id, user_id, curr_id, user_id)
            )
            fk_rows = cursor.fetchall()

            combined_neighbors = []
            seen_neighbors = set()
            for r in (link_rows + fk_rows):
                tgt_id = r[0]
                if tgt_id and tgt_id != curr_id and tgt_id not in seen_neighbors:
                    seen_neighbors.add(tgt_id)
                    combined_neighbors.append((tgt_id, r[1], float(r[2])))

            for target_id, relation, weight in combined_neighbors:
                if target_id in visited_ids:
                    continue

                # Fetch full target node from memories_v2 to ensure it is still active/not deleted
                cursor.execute(
                    """
                    SELECT
                        ref_id,
                        content,
                        type,
                        importance_score,
                        access_ratio,
                        initial_date,
                        state,
                        node_life,
                        expires_at,
                        linkable,
                        ref_link,
                        entities
                    FROM memories_v2
                    WHERE ref_id = %s
                      AND user_id = %s
                      AND type != 'delete'
                      AND state NOT IN ('deleted', 'expired')
                    """,
                    (target_id, user_id)
                )
                tgt_row = cursor.fetchone()
                if not tgt_row:
                    continue

                # Check real-time expiration
                node_life = tgt_row[7]
                init_date = tgt_row[5]
                exp_at = tgt_row[8]
                is_perm = (tgt_row[6] == 'permanent' or node_life is None or node_life == -1)

                if not is_perm:
                    expired = False
                    if exp_at:
                        try:
                            exp_dt = exp_at if isinstance(exp_at, datetime.datetime) else datetime.datetime.fromisoformat(str(exp_at))
                            if now_dt >= exp_dt:
                                expired = True
                        except Exception:
                            pass
                    if not expired and init_date and node_life is not None:
                        try:
                            init_dt = init_date if isinstance(init_date, datetime.datetime) else datetime.datetime.fromisoformat(str(init_date))
                            if (now_dt - init_dt).total_seconds() / 3600 >= node_life:
                                expired = True
                        except Exception:
                            pass
                    if expired:
                        continue

                target_linkable = bool(tgt_row[9])
                visited_ids.add(target_id)

                node_dict = {
                    "id": tgt_row[0],
                    "content": tgt_row[1],
                    "type": tgt_row[2],
                    "importance_score": float(tgt_row[3]),
                    "access_ratio": float(tgt_row[4]),
                    "created_at": str(tgt_row[5]),
                    "state": tgt_row[6],
                    "node_life": node_life,
                    "expires_at": str(exp_at) if exp_at else None,
                    "linkable": target_linkable,
                    "ref_link": tgt_row[10],
                    "relation": relation,
                    "graph_weight": weight,
                    "graph_depth": depth + 1,
                    "linked_to_seed": seed_id
                }

                seed_connected.append(node_dict)
                total_fetched += 1

                # "if the linkable is true and if the fetched score is high then you just keep on fetching rows until there are linkables right?"
                # If this newly fetched node is linkable, queue it up to keep expanding the graph!
                if target_linkable:
                    queue.append((target_id, depth + 1))

        linked_results[seed_id] = seed_connected

    return linked_results


def reinforce_links(cursor, node_ids: List[int], user_id: int):
    """
    Strengthens graph connections when multiple nodes are co-retrieved (Hebbian learning).
    """
    if len(node_ids) < 2:
        return
    try:
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                n1, n2 = node_ids[i], node_ids[j]
                cursor.execute(
                    """
                    UPDATE memory_links
                    SET weight = weight + 0.05
                    WHERE user_id = %s AND (
                        (source_id = %s AND target_id = %s) OR
                        (source_id = %s AND target_id = %s)
                    )
                    """,
                    (user_id, n1, n2, n2, n1)
                )
    except Exception:
        pass
