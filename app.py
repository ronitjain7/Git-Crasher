import uvicorn
import gradio as gr
from sql_env.server import app as fastapi_app
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
            # Safe import so we get the singleton env dynamically
            from sql_env.server import env
            obs = await env.reset(task_id)
            
            # Format status
            st = env.state()
            status_text = f"**Step:** {st['current_step']} / {st['max_steps']} | **Done:** {st['done']} | **Total Score:** {st['last_reward']:.2f}"
            
            return (
                obs.expected_hint,
                obs.db_schema,
                obs.query,
                obs.error_message or "No errors during reset phase.",
                {}, # Clear reward box
                status_text
            )
            
        async def ui_step(sql_string):
            from sql_env.server import env
            
            # Submitting the step correctly to the async server
            reward = await env.step(SQLAction(sql=sql_string))
            
            st = env.state()
            status_text = f"**Step:** {st['current_step']} / {st['max_steps']} | **Done:** {st['done']} | **Total Score:** {st['last_reward']:.2f}"
            
            r_val = reward.dict()
            # Surface any SQLite error from the grader into the error box
            error_msg = (
                reward.info.get("error") or
                reward.info.get("validation_error") or
                reward.info.get("plan_error") or
                "✅ No errors — SQL executed cleanly."
            )
            return r_val, status_text, error_msg

        # --- Wiring Events ---
        
        reset_btn.click(
            fn=ui_reset, 
            inputs=[task_dropdown], 
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block]
        )
        
        submit_btn.click(
            fn=ui_step,
            inputs=[sql_input],
            outputs=[reward_box, status_block, error_box]
        )
        
        # Hydrate the view dynamically on initial startup
        demo.load(
            fn=ui_reset,
            inputs=[task_dropdown],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block]
        )
        
    return demo

demo = create_demo()

# Mount the interactive UI to the existing FastApi backend
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=7860)
