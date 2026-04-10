import uvicorn
import gradio as gr
import plotly.graph_objects as go

from sql_env.server import app as fastapi_app
from sql_env.env import SQLReviewEnv
from sql_env.models import SQLAction
from sql_env.tasks import TASKS

# Read custom CSS for Deep Space / Glassmorphism theme
with open("assets/style.css", "r") as f:
    custom_css = f.read()


def create_reward_chart(history):
    """Real-time reward progression chart using Plotly."""
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
        xaxis=dict(title="Episode Steps", range=[0, 8], dtick=1, autorange=False, gridcolor="rgba(255,255,255,0.1)"),
        yaxis=dict(title="Reward Value [0, 1]", range=[0, 1.05], gridcolor="rgba(255,255,255,0.1)"),
        margin=dict(l=40, r=40, t=60, b=40),
        height=300
    )
    return fig


def get_safe_status(st):
    """Defensive status formatter — never crashes even if state dict is malformed."""
    try:
        step = st.get('current_step', 0)
        max_s = st.get('max_steps', 8)
        done = st.get('done', False)
        reward = float(st.get('last_reward', 0.0))
        return f"**STEP:** {step} / {max_s} | **DONE:** {done} | **SCORE:** {reward:.2f}"
    except Exception:
        return "**STEP:** ? / ? | **DONE:** ? | **SCORE:** 0.00"


def create_demo():
    # Gradio 6.0 compatibility: CSS needs to go to mount_gradio_app
    with gr.Blocks(title="SQL Review Environment") as demo:
        session_env = gr.State(None)
        
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
                # lines=3 ensures long hints (e.g. schema-design) are not truncated
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
                submit_btn = gr.Button("▶️ Execute & Submit Step", variant="secondary", elem_id="submit-btn")

                gr.Markdown("### 📊 Reward Progression")
                reward_chart = gr.Plot(label="Reward Signal", value=create_reward_chart([0.0]))

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 🏆 Feedback Phase")
                with gr.Row():
                    error_box = gr.Textbox(label="Execution Feedback", interactive=False, lines=2)
                    reward_box = gr.JSON(label="Detailed Reward Signal", value={})

        # --- Internal Logic ---

        async def ui_reset(task_id, current_env):
            try:
                if current_env is None:
                    current_env = SQLReviewEnv()
                obs = await current_env.reset(task_id)
                st = current_env.state()
                status_text = get_safe_status(st)

                # If query is empty (schema-design task), show a helpful SQL placeholder
                query_display = obs.query if obs.query.strip() else (
                    "-- Design your schema here. Use SQLite syntax only.\n"
                    "-- Example: CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL);"
                )

                return (
                    obs.expected_hint,
                    obs.db_schema,
                    query_display,
                    obs.error_message or "✅ Environment Ready.",
                    {},  # Clear reward box
                    status_text,
                    gr.update(interactive=True, value="▶️ Execute & Submit Step"),
                    create_reward_chart(st.get('history', [0.0])),
                    current_env
                )
            except Exception as e:
                return (
                    "Error", "Error", "-- Error --",
                    f"❌ Initialization Error: {str(e)}",
                    {}, "ERROR",
                    gr.update(),
                    create_reward_chart([0.0]),
                    current_env
                )

        async def ui_step(sql_string, current_env):
            try:
                reward = await current_env.step(SQLAction(sql=sql_string))
                st = current_env.state()
                done = reward.done
                status_text = get_safe_status(st)

                error_msg = (
                    reward.info.get("error") or
                    reward.info.get("validation_error") or
                    reward.info.get("plan_error") or
                    "✅ No errors — SQL executed cleanly."
                )

                # Visual done indicator — disable submit button when episode ends
                btn_update = gr.update(
                    interactive=not done,
                    value="✅ Episode Complete — Click Reset to Start Again" if done else "▶️ Execute & Submit Step"
                )

                return (
                    reward.model_dump(),
                    status_text,
                    error_msg,
                    btn_update,
                    create_reward_chart(st.get('history', [0.0])),
                    current_env
                )
            except Exception as e:
                return (
                    {"error": str(e)}, "ERROR",
                    f"❌ Step Error: {str(e)}",
                    gr.update(),
                    create_reward_chart([0.0]),
                    current_env
                )

        # --- Wiring Events ---
        reset_btn.click(
            fn=ui_reset,
            inputs=[task_dropdown, session_env],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block, submit_btn, reward_chart, session_env]
        )

        submit_btn.click(
            fn=ui_step,
            inputs=[sql_input, session_env],
            outputs=[reward_box, status_block, error_box, submit_btn, reward_chart, session_env]
        )

        demo.load(
            fn=ui_reset,
            inputs=[task_dropdown, session_env],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block, submit_btn, reward_chart, session_env]
        )

    return demo


demo = create_demo()
# Mount CSS dynamically for Gradio 6 compat
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui", css=custom_css)

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=7860, proxy_headers=True, forwarded_allow_ips="*")
