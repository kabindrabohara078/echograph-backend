from embedding import generate_embedding
from database import conn




def memory_cleanup():
    # =====================================================
    # OPTIONAL: TEMP MEMORY CLEANUP (keep if needed)
    # =====================================================

    cursor.execute(
        """
        DELETE FROM memories_v2
        WHERE user_id = %s
        AND node_life <= 0
        RETURNING content
        """,
        (user_id,)
    )

    deleted_rows = cursor.fetchall()

    conn.commit()

    print("Deleted temporary memories:", deleted_rows)


def search_nodes():
    
    # =====================================================
    # SEARCH QUERY (NO DECAY LOGIC HERE)
    # =====================================================
    cursor.execute(
        """
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
            state = 'active'
            AND user_id = %s

        ORDER BY final_rank DESC
        LIMIT 5
        """,
        (query_embedding, query_embedding, user_id)
    )

    results = cursor.fetchall()

    print("\n=========== SEARCH RESULTS ===========")
    if not results:
        print("\n++++++++++++ EMPTY RESULTS +++++++++++++++")
        return 0
    for row in results:
        print(row)
    print("\n======================================\n")


    return results


def retrieve_context(current_user, search):

    user_id = int(current_user)

    query_embedding = generate_embedding(search.query)

    cursor = conn.cursor()

    memory_cleanup()
    print("Memory cleaned")

    db_response = search_nodes()

    if db_response:
        # =====================================================
        # FILTER HIGH CONFIDENCE RESULTS
        # =====================================================
        filtered_rows = [
            row[0]
            for row in db_response
            if row[6] < 0.5
        ]


        # =====================================================
        # UPDATE ACCESS_RATIO
        # =====================================================
        if filtered_rows:
            cursor.execute(
                """
                UPDATE memories_v2
                SET
                    access_ratio = access_ratio * 1.05,
                    last_accessed = NOW()
                WHERE ref_id = ANY(%s)
                """,
                (filtered_rows,)
            )


            context_nodes = []

            for row in filtered_rows:
               
                context_nodes.append({
                        "id": row[0],
                        "content": row[1],
                        "type": row[2],
                        "importance_score": row[3],
                        "access_ratio": row[4],
                        "created_at": row[5],
                        "distance": float(row[6]),
                        "final_rank": float(row[7])
                    })
            conn.commit()
                # =====================================================
                # SUCCESS RESPONSE
                # =====================================================
            return {
                    "results": context_nodes,
                    "count": len(context_nodes),
                    "user_id": user_id
            }
        else:
            conn.commit()
            return 
            {
                "results": [],
                "message": "No high confidence context exists for the user of given type"
            }
    else:
        conn.commit()
        if not context_nodes:
            return 
            {
                "results": [],
                "message": "No context exists for the user of given type"
            }

