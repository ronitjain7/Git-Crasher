import uvicorn
import gradio as gr
import plotly.graph_objects as go

from sql_env.server import app as fastapi_app
from sql_env.env import SQLReviewEnv
from sql_env.models import SQLAction
from sql_env.tasks import TASKS

# Read custom CSS for Enterprise theme
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
        line=dict(color='#1f6feb', width=3),
        marker=dict(size=8, color='#1f6feb')
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"),
        xaxis=dict(
            title=dict(text="Episode Steps", font=dict(color='#888888')), 
            range=[0, 8], dtick=1, autorange=False, 
            showgrid=True, gridcolor='rgba(128,128,128,0.15)',
            zeroline=False, showline=True, linewidth=1, 
            linecolor='#888888', tickfont=dict(color='#888888')
        ),
        yaxis=dict(
            title=dict(text="Reward Value [0, 1]", font=dict(color='#888888')), 
            range=[0, 1.05], dtick=0.1,
            showgrid=True, gridcolor='rgba(128,128,128,0.15)',
            zeroline=False, showline=True, linewidth=1, 
            linecolor='#888888', tickfont=dict(color='#888888')
        ),
        margin=dict(l=40, r=20, t=10, b=40),
        height=360  # Adjust this value to increase/decrease the Episode Metrics height
    )
    return fig


def get_safe_status(st):
    """Defensive HTML status formatter — responsive HTML chips bounded by CSS."""
    try:
        step = st.get('current_step', 0)
        max_s = st.get('max_steps', 8)
        done = st.get('done', False)
        reward = float(st.get('last_reward', 0.0))
        
        return f"""
        <div class="kpi-wrapper">
            <span class="kpi-chip step">STEP {step}/{max_s}</span>
            <span class="kpi-chip">DONE {done}</span>
            <span class="kpi-chip">SCORE {reward:.2f}</span>
        </div>
        """
    except Exception:
        return "<div class='kpi-wrapper'>Error Loading State</div>"


def create_demo():
    with gr.Blocks(title="SQL Review Environment") as demo:
        session_env = gr.State(None)
        
        # 4. Hero / Navbar (Updated with HTML spans)
        gr.Markdown(
            "<span class='hero-emoji'>🗄️</span> **SQL Review Environment — Dashboard** <br>"
            "<span class='hero-subtitle'> Train | Review | Optimize <br>"
            "Welcome to the OpenEnv SQL training environment. Act as an agent directly, iterate on broken SQL, and receive dense evaluation rewards!"
            "</span>", 
            elem_classes=["hero-bar"]
        )
        
        # --- ROW 1: Context & Action ---
        with gr.Row():
            
            # Q1: STATE (S_t)
            with gr.Column(scale=1):
                gr.Markdown("### 📡 State Observation (S_t)", elem_classes=["section-header"])
                
                with gr.Row(equal_height=True):
                    task_dropdown = gr.Dropdown(
                        choices=list(TASKS.keys()), value="syntax-fix",
                        interactive=True, label="Task ID", scale=3,
                        elem_id="task-dropdown"
                    )
                    reset_btn = gr.Button("🔄 Reset Environment", variant="secondary", scale=1, elem_id="reset-btn")
                
                hint_box = gr.Textbox(label="Expected Hint", interactive=False, lines=2)
                schema_box = gr.Textbox(label="Database Schema", interactive=False, lines=2)
                
            # Q2: ACTION (A_t)
            with gr.Column(scale=1):
                gr.Markdown("### ⌨️ Agent Action (A_t)", elem_classes=["section-header"])
                
                status_block = gr.HTML(get_safe_status({}))
                
                # Fused IDE Group mapping
                with gr.Column(elem_classes=["ide-group"]):
                    sql_input = gr.Code(label="SQL Code Editor", language="sql", lines=9, value="")
                    submit_btn = gr.Button("▶️ Execute & Submit Step", variant="primary")

        # --- ROW 2: Feedback & Metrics ---
        with gr.Row():
            
            # Q3: REWARD SIGNAL (R_t)
            with gr.Column(scale=1):
                gr.Markdown("### 🏆 Reward Signal (R_t)", elem_classes=["section-header"])
                
                error_box = gr.Textbox(label="Execution Error (if any)", interactive=False, lines=1)
                reward_box = gr.JSON(label="Structured Reward", value={}, elem_classes=["json-container"])
                
            # Q4: METRICS
            with gr.Column(scale=1):
                gr.Markdown("### 📊 Episode Metrics", elem_classes=["section-header"])
                
                reward_chart = gr.Plot(label="", value=create_reward_chart([0.0]))

        # --- Internal Application Logic ---

        async def ui_reset(task_id, current_env):
            try:
                if current_env is None:
                    current_env = SQLReviewEnv()
                obs = await current_env.reset(task_id)
                st = current_env.state()
                status_html = get_safe_status(st)

                query_display = obs.query if obs.query.strip() else (
                    "-- Design your schema here. Use SQLite syntax only.\n"
                    "-- Example: CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL);"
                )

                return (
                    obs.expected_hint,
                    obs.db_schema,
                    query_display,
                    obs.error_message or "✅ Environment Ready.",
                    {},
                    status_html,
                    gr.update(interactive=True, value="▶️ Execute & Submit Step"),
                    create_reward_chart(st.get('history', [0.0])),
                    current_env
                )
            except Exception as e:
                return (
                    "Error", "Error", "-- Error --",
                    f"❌ Initialization Error: {str(e)}",
                    {}, get_safe_status({}),
                    gr.update(),
                    create_reward_chart([0.0]),
                    current_env
                )

        async def ui_step(sql_string, current_env):
            try:
                reward = await current_env.step(SQLAction(sql=sql_string))
                st = current_env.state()
                done = reward.done
                status_html = get_safe_status(st)

                error_msg = (
                    reward.info.get("error") or
                    reward.info.get("validation_error") or
                    reward.info.get("plan_error") or
                    "✅ No errors — SQL executed cleanly."
                )

                btn_update = gr.update(
                    interactive=not done,
                    value="✅ Episode Complete — Reset to Start Again" if done else "▶️ Execute & Submit Step"
                )

                return (
                    reward.model_dump(),
                    status_html,
                    error_msg,
                    btn_update,
                    create_reward_chart(st.get('history', [0.0])),
                    current_env
                )
            except Exception as e:
                return (
                    {"error": str(e)}, get_safe_status({}),
                    f"❌ Step Error: {str(e)}",
                    gr.update(),
                    create_reward_chart([0.0]),
                    current_env
                )

        # --- Wiring Events ---
        
        # 1. Reset Button Click
        reset_btn.click(
            fn=ui_reset,
            inputs=[task_dropdown, session_env],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block, submit_btn, reward_chart, session_env]
        )
        
        # 2. Dynamic Dropdown Change instantly updates Environment Context
        task_dropdown.change(
            fn=ui_reset,
            inputs=[task_dropdown, session_env],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block, submit_btn, reward_chart, session_env]
        )

        # 3. Step Submission
        submit_btn.click(
            fn=ui_step,
            inputs=[sql_input, session_env],
            outputs=[reward_box, status_block, error_box, submit_btn, reward_chart, session_env]
        )
        
        # 4. Initial Launch Hydration
        demo.load(
            fn=ui_reset,
            inputs=[task_dropdown, session_env],
            outputs=[hint_box, schema_box, sql_input, error_box, reward_box, status_block, submit_btn, reward_chart, session_env]
        )

    return demo


demo = create_demo()
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui", css=custom_css)

if __name__ == '__main__':
    uvicorn.run("app:app", host="0.0.0.0", port=7860, proxy_headers=True, forwarded_allow_ips="*")