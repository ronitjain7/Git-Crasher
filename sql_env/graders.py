import sqlite3
from .tasks import get_master_db

def _rows_to_set(rows):
    # Sort by string representation to safely handle SQLite NULL (NoneType) differences in LEFT JOINs
    return sorted([tuple(row) for row in rows], key=lambda x: str(x))

def get_table_details(conn):
    """Extract full PRAGMA structural definitions to precisely grade DDL queries."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cursor.fetchall()]
    schema = {}
    for t in tables:
        cursor.execute(f"PRAGMA table_info([{t}])")
        ti = _rows_to_set(cursor.fetchall())
        cursor.execute(f"PRAGMA foreign_key_list([{t}])")
        fk = _rows_to_set(cursor.fetchall())
        schema[t.lower()] = (ti, fk)
    return schema

def dump_all_data(conn):
    """Extract all table rows globally to precisely grade DML queries."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cursor.fetchall()]
    data = {}
    for t in tables:
        cursor.execute(f"SELECT * FROM [{t}]")
        data[t.lower()] = _rows_to_set(cursor.fetchall())
    return data

def grade_sql(task_id, conn, agent_sql, expected_sql, step, max_steps):
    breakdown = {
        "syntax": 0.0,
        "execution": 0.0,
        "correctness": 0.0,
        "performance": 0.0,
        "penalty": 0.0
    }
    info = {}

    if step >= max_steps:
        breakdown["penalty"] -= 0.10

    upper_sql = agent_sql.upper().strip()
    upper_expected = expected_sql.upper().strip()

    # Penalties for catastrophic destruction without WHERE clauses
    if ("DROP " in upper_sql or "DELETE " in upper_sql) and "WHERE " not in upper_sql:
        breakdown["penalty"] -= 0.05

    cursor = conn.cursor()

    # Intent Classification Header
    is_dql = upper_expected.startswith("SELECT") or upper_expected.startswith("WITH")
    is_ddl = upper_expected.startswith("CREATE") or upper_expected.startswith("ALTER") or upper_expected.startswith("DROP")
    is_dml = upper_expected.startswith("INSERT") or upper_expected.startswith("UPDATE") or upper_expected.startswith("DELETE")

    if is_dql:
        try:
            cursor.execute(f"EXPLAIN {agent_sql}")
            breakdown["syntax"] = 0.30
        except Exception as e:
            info["error"] = str(e)

        try:
            cursor.execute(agent_sql)
            agent_results = cursor.fetchall()
            breakdown["syntax"] = 0.30 
            breakdown["execution"] = 0.25
            
            try:
                cursor.execute(expected_sql)
                expected_results = cursor.fetchall()

                if _rows_to_set(agent_results) == _rows_to_set(expected_results):
                    breakdown["correctness"] = 0.35

                    # Preserve EXPLAIN QUERY PLAN performance checks explicitly for DQL
                    try:
                        cursor.execute(f"EXPLAIN QUERY PLAN {agent_sql}")
                        plan_rows = cursor.fetchall()
                        plan_str = " ".join([str(tuple(r)).upper() for r in plan_rows])

                        doing_full_scans = ("SCAN TABLE" in plan_str)
                        if "INDEX" in plan_str or "SEARCH TABLE" in plan_str or not doing_full_scans:
                             breakdown["performance"] = 0.10
                             
                        # Explicit legacy support for performance-tune full-scan logic 
                        if task_id == "performance-tune":
                            if ("SCAN TABLE ORDERS" in plan_str and "SCAN TABLE USERS" in plan_str):
                                breakdown["performance"] = 0.0
                            else:
                                breakdown["performance"] = 0.10
                    except Exception as e:
                        info["plan_error"] = str(e)
            except Exception as e:
                info["validation_error"] = str(e)
        except Exception as e:
            info["error"] = str(e)

    elif is_dml:
        # Data manipulation: Need clean slate to compare mutations identically
        master = get_master_db(task_id)
        expected_conn = sqlite3.connect(":memory:")
        expected_conn.row_factory = sqlite3.Row
        master.backup(expected_conn)
        
        try:
            cursor.execute(f"EXPLAIN {agent_sql}")
            breakdown["syntax"] = 0.30
        except sqlite3.Error as e:
            info["error"] = str(e)
            
        try:
            # Use execute() (not executescript) so the progress_handler timeout remains active
            cursor.execute(agent_sql)
            breakdown["syntax"] = 0.30
            breakdown["execution"] = 0.25
            
            try:
                expected_conn.executescript(expected_sql)
                
                # Compare full datasets natively
                agent_data = dump_all_data(conn)
                expected_data = dump_all_data(expected_conn)
                
                if agent_data == expected_data:
                    breakdown["correctness"] = 0.35
                    breakdown["performance"] = 0.10
            except Exception as e:
                info["validation_error"] = str(e)
        except Exception as e:
            info["error"] = str(e)
        finally:
            expected_conn.close()

    elif is_ddl:
        master = get_master_db(task_id)

        # Fresh ephemeral clone for the agent's SQL — never pollute the live conn
        agent_conn = sqlite3.connect(":memory:")
        agent_conn.row_factory = sqlite3.Row
        master.backup(agent_conn)

        # Separate clone for the expected (validation) SQL
        expected_conn = sqlite3.connect(":memory:")
        expected_conn.row_factory = sqlite3.Row
        master.backup(expected_conn)

        try:
            agent_conn.executescript(agent_sql)
            breakdown["syntax"] = 0.30
            breakdown["execution"] = 0.25

            try:
                expected_conn.executescript(expected_sql)

                # Diff schemas using PRAGMA on the two ephemeral clones
                agent_schema = get_table_details(agent_conn)
                expected_schema = get_table_details(expected_conn)

                if agent_schema == expected_schema:
                    breakdown["correctness"] = 0.35
                    breakdown["performance"] = 0.10
                else:
                    # Partial credit: correct table names but column/FK mismatch
                    if set(agent_schema.keys()) == set(expected_schema.keys()):
                        breakdown["correctness"] = 0.15
            except sqlite3.Error as e:
                info["validation_error"] = str(e)
        except sqlite3.Error as e:
            info["error"] = str(e)
            try:
                first_stmt = agent_sql.strip().rstrip(";").split(";")[0]
                agent_conn.execute(f"EXPLAIN {first_stmt}")
                breakdown["syntax"] = 0.30
            except Exception:
                pass
        finally:
            agent_conn.close()
            expected_conn.close()
            
    total_reward = sum(breakdown.values())
    total_reward = max(0.01, min(0.99, float(total_reward)))  
    done = total_reward >= 0.9 or step >= max_steps

    total_reward = round(total_reward, 2)
    for k in breakdown:
        breakdown[k] = round(breakdown[k], 2)

    return total_reward, breakdown, done, info
