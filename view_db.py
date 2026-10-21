import os
import sys
import sqlite3

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def view_database():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "echograph_local.db")

    if not os.path.exists(db_path):
        print(f"[!] Database file not found at: {db_path}")
        return

    print("=" * 80)
    print(f"[EchoGraph Local Database]: {db_path}")
    print("=" * 80)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Show Users
    print("\n👥 Registered Users:")
    print("-" * 80)
    cur.execute("SELECT id, email, fname, lname FROM users ORDER BY id ASC;")
    users = cur.fetchall()
    for u in users:
        print(f"  User ID #{u[0]}: {u[1]} ({u[2]} {u[3]})")

    # 2. Show Memories
    print("\n📦 Stored Memories (Table: memories_v2):")
    print("-" * 80)
    query = """
        SELECT
            m.ref_id,
            u.email,
            m.type,
            m.importance_score,
            m.state,
            m.node_life,
            m.initial_date,
            m.expires_at,
            m.linkable,
            m.ref_link,
            m.entities,
            m.content
        FROM memories_v2 m
        JOIN users u ON m.user_id = u.id
        ORDER BY m.ref_id DESC;
    """
    cur.execute(query)
    rows = cur.fetchall()

    if not rows:
        print("  (No memories found in database yet.)")
    else:
        print(f"  Total Entries: {len(rows)}\n")
        for r in rows:
            ref_id, email, m_type, importance, state, node_life, initial_date, expires_at, linkable, ref_link, entities, content = r
            life_str = "Permanent (No Expiry)" if state == "permanent" or node_life is None or node_life == -1 else f"{node_life}h left"
            exp_str = expires_at or "Never (Permanent)"
            link_flag = "True" if linkable else "False"
            parent_str = f"Parent ID #{ref_link}" if ref_link else "None (Root/Independent)"
            ent_str = entities if entities else "[]"
            print(f"  [ID #{ref_id}] User: {email} | Category: [{m_type.upper()}] | Importance: {importance}")
            print(f"    Lifespan: {life_str} | Expires: {exp_str} | State: {state} | Created: {initial_date}")
            print(f"    Graph: Linkable: {link_flag} | Ref Link: {parent_str} | Entities: {ent_str}")
            print(f"    Content: \"{content}\"")
            print("  " + "-" * 76)

    # 3. Show Knowledge Graph Edges (memory_links)
    print("\n🕸️  Memory Knowledge Graph Edges (Table: memory_links):")
    print("-" * 80)
    try:
        cur.execute("""
            SELECT
                l.id,
                u.email,
                l.source_id,
                l.target_id,
                l.relation_type,
                l.weight,
                m1.content,
                m2.content
            FROM memory_links l
            JOIN users u ON l.user_id = u.id
            LEFT JOIN memories_v2 m1 ON l.source_id = m1.ref_id
            LEFT JOIN memories_v2 m2 ON l.target_id = m2.ref_id
            ORDER BY l.id ASC;
        """)
        links = cur.fetchall()
        if not links:
            print("  (No graph links formed yet.)")
        else:
            print(f"  Total Edges: {len(links)}\n")
            for edge in links:
                eid, email, src, tgt, rel, weight, c1, c2 = edge
                c1_trunc = (c1[:35] + '...') if c1 and len(c1) > 35 else (c1 or "")
                c2_trunc = (c2[:35] + '...') if c2 and len(c2) > 35 else (c2 or "")
                print(f"  [Edge #{eid}] User: {email} | Weight: {weight:.2f}")
                print(f"    Node #{src} (\"{c1_trunc}\")")
                print(f"      └──[{rel}]──> Node #{tgt} (\"{c2_trunc}\")")
                print("  " + "-" * 76)
    except Exception as e:
        print("  (Error querying memory_links:", e, ")")

    print("=" * 80 + "\n")

if __name__ == "__main__":
    view_database()
