import sqlite3
import hashlib

def hash_results(results):
    hasher = hashlib.sha256()
    for row in results:
        hasher.update(str(tuple(row)).encode('utf-8'))
    return hasher.hexdigest()

def grade_sql(task_id, conn, agent_sql, expected_sql, step, max_steps):
    breakdown = {
        "syntax": 0.0,
        "execution": 0.0,
        "correctness": 0.0,
        "performance": 0.0,
        "penalty": 0.0
    }
    
    if step >= max_steps:
        breakdown["penalty"] -= 0.10
        
    upper_sql = agent_sql.upper()
    if ("DROP " in upper_sql or "DELETE " in upper_sql) and "WHERE " not in upper_sql:
        breakdown["penalty"] -= 0.05
        
    cursor = conn.cursor()
    
    if task_id == "schema-design":
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        initial_tables = {row[0].lower() for row in cursor.fetchall()}
        
        try:
            cursor.executescript(agent_sql)
            breakdown["syntax"] = 0.30
            breakdown["execution"] = 0.25
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            final_tables = {row[0].lower() for row in cursor.fetchall()}
            new_tables = final_tables - initial_tables
            
            if len(new_tables) >= 3:
                 expected = {"messages", "posts", "likes", "follows", "followers", "users", "user"}
                 matches = len(new_tables.intersection(expected))
                 if matches >= 2:
                     breakdown["correctness"] = 0.35
                     breakdown["performance"] = 0.10
                 else:
                     breakdown["correctness"] = 0.15
                     
            for t in new_tables:
                 cursor.execute(f"DROP TABLE IF EXISTS {t}")
                 
        except sqlite3.Error:
            try:
                cursor.execute(f"EXPLAIN {agent_sql}")
                breakdown["syntax"] = 0.30
            except sqlite3.Error:
                pass
            
            # Reset any partially created tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            current_tables = {row[0].lower() for row in cursor.fetchall()}
            for t in current_tables - initial_tables:
                 cursor.execute(f"DROP TABLE IF EXISTS {t}")
    else:
        try:
            cursor.execute(f"EXPLAIN {agent_sql}")
            breakdown["syntax"] = 0.30
        except sqlite3.Error:
            pass

        try:
            cursor.execute(agent_sql)
            agent_results = cursor.fetchall()
            breakdown["syntax"] = 0.30 
            breakdown["execution"] = 0.25
            
            cursor.execute(expected_sql)
            expected_results = cursor.fetchall()
            
            if hash_results(agent_results) == hash_results(expected_results):
                breakdown["correctness"] = 0.35
                
                if task_id == "performance-tune":
                    cursor.execute(f"EXPLAIN QUERY PLAN {agent_sql}")
                    plan_rows = cursor.fetchall()
                    plan_str = " ".join([str(tuple(r)).upper() for r in plan_rows])
                    if "SCAN TABLE orders" in plan_str and "SCAN TABLE users" in plan_str:
                        pass
                    elif "SCAN TABLE" not in plan_str or "SEARCH TABLE" in plan_str or "INDEX" in plan_str:
                        breakdown["performance"] = 0.10
                else:
                    breakdown["performance"] = 0.10
        except sqlite3.Error as e:
            pass
            
    total_reward = sum(breakdown.values())
    total_reward = max(0.01, min(0.99, float(total_reward)))  # strictly within (0, 1) per validator
    done = total_reward >= 0.9 or step >= max_steps
    
    total_reward = round(total_reward, 2)
    for k in breakdown:
         breakdown[k] = round(breakdown[k], 2)
    
    return total_reward, breakdown, done, {}
