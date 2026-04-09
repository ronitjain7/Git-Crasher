import uvicorn
import gradio as gr
from sql_env.server import app as fastapi_app, env, env_lock
from sql_env.models import SQLAction
from sql_env.tasks import TASKS

def create_demo():
    with gr.Blocks(title="SQL Review Environment") as demo:
        gr.Markdown('''
        # 🗄️ SQL Review Environment Dashboard
        ### Train | Review | Optimize
        Welcome to the OpenEnv SQL training environment. Act as an agent directly, iterate on broken SQL, and receive dense evaluation rewards!
        ''')
        
        with gr.Row():
            with gr.Column(scale=1):
                task_dropdown = gr.Dropdown(
                    choices=list(TASKS.keys()),
                    value="syntax-fix",
                    label="Select Task",
                    interactive=True
                )
                reset_btn = gr.Button("🔄 Reset Environment", variant="primary")
                
                gr.Markdown("### Episode Status")
                status_block = gr.Markdown("Waiting to load state...")
                
            with gr.Column(scale=2):
                gr.Markdown("### Observation Space")
                hint_box = gr.Textbox(label="Expected Hint", interactive=False)
                schema_box = gr.Textbox(label="Database Schema", interactive=False, lines=2)
        
        gr.Markdown("---")
        gr.Markdown("### Agent Action: SQL Input")
        sql_input = gr.Code(label="Query Editor", language="sql", lines=15, value="-- Click Reset to load the task query.")
        submit_btn = gr.Button("▶️ Execute & Submit Step", variant="secondary")
        
        gr.Markdown("---")
        gr.Markdown("### 🏆 Reaction & Reward (Feedback Phase)")
        with gr.Row():
            error_box = gr.Textbox(label="Execution Error (if any)", interactive=False, lines=2)
            reward_box = gr.JSON(label="Detailed Reward Signal", value={})

        # --- Internal Application Logic ---
        
        async def ui_reset(task_id):
            async with env_lock:
                obs = await env.reset(task_id)

            st = env.state()
            status_text = f"**Step:** {st['current_step']} / {st['max_steps']} | **Done:** {st['done']} | **Total Score:** {st['last_reward']:.2f}"

            return (
                obs.expected_hint,
                obs.db_schema,
                obs.query,
                obs.error_message or "No errors during reset phase.",
                {},  # Clear reward box
                status_text,
                gr.update(interactive=True, value="▶️ Execute & Submit Step")  # Re-enable btn
            )
            
        async def ui_step(sql_string):
            async with env_lock:
                reward = await env.step(SQLAction(sql=sql_string))

            st = env.state()
            done = reward.done
            status_text = f"**Step:** {st['current_step']} / {st['max_steps']} | **Done:** {done} | **Total Score:** {st['last_reward']:.2f}"

            r_val = reward.model_dump()
            error_msg = (
                reward.info.get("error") or
                reward.info.get("validation_error") or
                reward.info.get("plan_error") or
                "✅ No errors — SQL executed cleanly."
            )

            # Fix 10: Visual done indicator — disable submit button when episode ends
            btn_update = gr.update(
                interactive=not done,
                value="✅ Episode Complete — Click Reset to Start Again" if done else "▶️ Execute & Submit Step"
            )
            return r_val, status_text, error_msg, btn_update

        # --- Wiring Events ---
        
        reset_btn.click(
            fn=ui_reset,
            inputs=[task_dropdown],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block, submit_btn]
        )

        submit_btn.click(
            fn=ui_step,
            inputs=[sql_input],
            outputs=[reward_box, status_block, error_box, submit_btn]
        )

        # Hydrate the view dynamically on initial startup
        demo.load(
            fn=ui_reset,
            inputs=[task_dropdown],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block, submit_btn]
        )
        
    return demo

demo = create_demo()

# Mount the interactive UI at /ui; root redirect is handled in server.py
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == '__main__':
    # proxy_headers=True tells uvicorn to trust X-Forwarded-Proto: https from HF's load balancer
    # This ensures Gradio generates correct https:// iframe URLs, preventing mixed content errors
    uvicorn.run("app:app", host="0.0.0.0", port=7860, proxy_headers=True, forwarded_allow_ips="*")
