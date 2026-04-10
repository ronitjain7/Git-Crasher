import uvicorn
import gradio as gr
import plotly.graph_objects as go
from sql_env.server import app as fastapi_app, env, env_lock
from sql_env.models import SQLAction
from sql_env.tasks import TASKS

# Read custom CSS for Deep Space / Glassmorphism theme
with open("assets/style.css", "r") as f:
    custom_css = f.read()

def create_reward_chart(history):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(history))),
        y=history,
        mode='lines+markers',
        name='Reward Signal',
        line=dict(color='#38bdf8', width=3),
        marker=dict(size=8, color='#818cf8', line=dict(width=2, color='#ffffff'))
    ))
    fig.update_layout(
        title="📈 Real-Time Reward Signal Progress",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="#f1f5f9"),
        xaxis=dict(title="Episode Steps", gridcolor="rgba(255,255,255,0.1)"),
        yaxis=dict(title="Reward Value [0, 1]", range=[0, 1.05], gridcolor="rgba(255,255,255,0.1)"),
        margin=dict(l=40, r=40, t=60, b=40),
        height=300
    )
    return fig

def get_safe_status(st):
    try:
        step = st.get('current_step', 0)
        max_s = st.get('max_steps', 8)
        done = st.get('done', False)
        reward = float(st.get('last_reward', 0.0))
        return f"**STEP:** {step} / {max_s} | **DONE:** {done} | **SCORE:** {reward:.2f}"
    except Exception:
        return "**STEP:** ? / ? | **DONE:** ? | **SCORE:** 0.00"

def create_demo():
    with gr.Blocks(title="SQL Review Environment", css=custom_css) as demo:
        with gr.Row():
            gr.Markdown('''
            # 🗄️ SQL Review Environment — Dashboard
            ### High-Stakes Database Engineering Simulation
            Identify bugs, optimize queries, and design schemas in a live SQLite environment.
            ''', elem_classes=["hero-text"])
        
        with gr.Row():
            with gr.Column(scale=1):
                task_dropdown = gr.Dropdown(
                    choices=list(TASKS.keys()),
                    value="syntax-fix",
                    label="Active Objective",
                    interactive=True
                )
                reset_btn = gr.Button("🔄 Initialize Environment", variant="primary", elem_id="reset-btn")
                
                gr.Markdown("### 🛠️ Execution Status")
                status_block = gr.Markdown("Ready to initialize...", elem_id="status-block")
                
                gr.Markdown("---")
                gr.Markdown("### 📡 Observation Space")
                hint_box = gr.Textbox(label="Agent Goal & Intent", interactive=False, lines=3)
                schema_box = gr.Textbox(label="Live DB Schema Definition", interactive=False, lines=5)

            with gr.Column(scale=2):
                gr.Markdown("### ⌨️ Agent Action: SQL Input")
                sql_input = gr.Code(
                    label="Query Editor", 
                    language="sql", 
                    lines=14, 
                    value="-- Select a task and click Initialize."
                )
                submit_btn = gr.Button("▶️ Submit Step to Environment", variant="secondary", elem_id="submit-btn")
                
                gr.Markdown("### 📊 Reward Progression")
                reward_chart = gr.Plot(label="Reward Signal", value=create_reward_chart([0.0]))

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 🏆 Feedback Phase")
                with gr.Row():
                    error_box = gr.Textbox(label="Last Engine Feedback", interactive=False, lines=2)
                    reward_json = gr.JSON(label="Structured Reward Distribution")

        # --- Internal Logic ---

        async def ui_reset(task_id):
            try:
                async with env_lock:
                    obs = await env.reset(task_id)
                st = env.state()
                status_text = get_safe_status(st)
                return (
                    obs.expected_hint,
                    obs.db_schema,
                    obs.query or "-- Enter SQL here...",
                    obs.error_message or "✅ Environment Ready.",
                    {},
                    status_text,
                    gr.update(interactive=True, value="▶️ Submit Step to Environment"),
                    create_reward_chart(st['history'])
                )
            except Exception as e:
                return "Error", "Error", "-- Error --", f"❌ Initialization Error: {str(e)}", {}, "ERROR", gr.update(), create_reward_chart([0.0])

        async def ui_step(sql_string):
            try:
                async with env_lock:
                    reward = await env.step(SQLAction(sql=sql_string))
                st = env.state()
                done = reward.done
                status_text = get_safe_status(st)
                error_msg = (
                    reward.info.get("error") or 
                    reward.info.get("validation_error") or 
                    "✅ SQL Executed Cleanly."
                )
                btn_update = gr.update(
                    interactive=not done,
                    value="✅ Episode Terminated" if done else "▶️ Submit Step to Environment"
                )
                return (
                    reward.model_dump(), 
                    status_text, 
                    error_msg, 
                    btn_update,
                    create_reward_chart(st['history'])
                )
            except Exception as e:
                return {"error": str(e)}, "ERROR", f"❌ Step Error: {str(e)}", gr.update(), create_reward_chart([0.0])

        # --- Wiring Events ---
        reset_btn.click(
            fn=ui_reset,
            inputs=[task_dropdown],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_json, status_block, submit_btn, reward_chart]
        )

        submit_btn.click(
            fn=ui_step,
            inputs=[sql_input],
            outputs=[reward_json, status_block, error_box, submit_btn, reward_chart]
        )

        demo.load(
            fn=ui_reset,
            inputs=[task_dropdown],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_json, status_block, submit_btn, reward_chart]
        )

    return demo

demo = create_demo()
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=7860, proxy_headers=True, forwarded_allow_ips="*")
