import dash
from dash import Dash, html, dash_table, Input, Output, State
import requests
import pandas as pd

API_URL = "http://localhost:5000"
ENVIRONMENTS = ['dev', 'sit', 'uat', 'preprod']

app = Dash(__name__, suppress_callback_exceptions=True)

app.layout = html.Div(style={'padding': '40px', 'fontFamily': 'Arial, sans-serif', 'backgroundColor': '#f0f4f8', 'position': 'relative'}, children=[
    html.Img(src='/assets/logo.png', style={
        'position': 'absolute',
        'top': '20px',
        'right': '20px',
        'height': '60px',
        'width': 'auto'
    }),

    html.H2('OpenShift Deployments Dashboard', style={
        'color': '#1a237e', 'fontSize': '32px', 'fontWeight': 'bold', 'marginBottom': '30px'
    }),

    html.Div([
        html.Span('Environment:', style={'fontWeight': 'bold', 'marginRight': '15px', 'fontSize': '16px'}),
        html.Div([
            html.Button(env.upper(), id={'type': 'env-btn', 'index': env}, n_clicks=0, style={
                'marginRight': '12px',
                'padding': '10px 20px',
                'border': 'none',
                'borderRadius': '8px',
                'cursor': 'pointer',
                'color': 'white',
                'backgroundColor': '#90a4ae',
                'boxShadow': '0 3px 6px rgba(0,0,0,0.1)',
                'fontSize': '14px'
            }) for env in ENVIRONMENTS
        ], style={'display': 'inline-block'}),
    ], style={'marginBottom': '25px'}),

    html.Div(id='deployments-table', style={
        'marginTop': '30px', 'boxShadow': '0 4px 8px rgba(0,0,0,0.05)', 'borderRadius': '8px'
    }),

    html.H3('Pod Logs:', style={'marginTop': '40px', 'fontSize': '24px', 'color': '#37474f'}),
    html.Div(id='logs-container', style={
        'whiteSpace': 'pre-wrap',
        'backgroundColor': '#ffffff',
        'padding': '15px',
        'borderRadius': '8px',
        'height': '400px',
        'overflowY': 'scroll',
        'boxShadow': '0 4px 10px rgba(0,0,0,0.05)',
        'border': '1px solid #e0e0e0',
        'fontSize': '14px'
    }),

    html.Div(id='selected-env', style={'display': 'none'}, children='dev')
])

@app.callback(
    Output('deployments-table', 'children'),
    Output({'type': 'env-btn', 'index': dash.ALL}, 'style'),
    Output('selected-env', 'children'),
    Input({'type': 'env-btn', 'index': dash.ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def update_deployments(n_clicks_list):
    ctx = dash.callback_context
    env_selected = eval(ctx.triggered[0]['prop_id'].split('.')[0])['index']

    button_styles = [{
        'marginRight': '12px', 'padding': '10px 20px', 'border': 'none', 'borderRadius': '8px',
        'cursor': 'pointer', 'color': 'white', 'fontSize': '14px',
        'backgroundColor': '#3949ab' if env == env_selected else '#90a4ae',
        'boxShadow': '0 3px 6px rgba(0,0,0,0.1)',
        'fontWeight': 'bold' if env == env_selected else 'normal'
    } for env in ENVIRONMENTS]

    response = requests.get(f"{API_URL}/{env_selected}")
    if response.status_code != 200 or not response.json():
        return html.Div('Failed to fetch deployments.', style={'color': 'red'}), button_styles, env_selected

    deployments = response.json()
    for dep in deployments:
        ready = dep.get("ready", "")
        try:
            ready_replicas, total_replicas = map(int, ready.split('/'))
            dep["status"] = "Running ✅" if ready_replicas == total_replicas and total_replicas > 0 else "Not Ready ❌"
        except:
            dep["status"] = "Unknown ⚠️"
        dep.pop("ready", None)

    df = pd.DataFrame(deployments)

    if 'route' in df.columns:
        df['route'] = df['route'].apply(lambda x: f"[Open Route]({x})" if x else "No Route")

    return dash_table.DataTable(
        id='table',
        columns=[
            {"name": "Name", "id": "name"},
            {"name": "Image", "id": "image"},
            {"name": "Route", "id": "route", "presentation": "markdown"},
            {"name": "Status", "id": "status"}
        ],
        data=df.to_dict('records'),
        row_selectable='single',
        selected_rows=[],
        style_table={'overflowX': 'auto', 'borderRadius': '8px'},
        style_header={'backgroundColor': '#1a237e', 'color': 'white', 'fontWeight': 'bold', 'fontSize': '15px'},
        style_cell={'padding': '12px', 'textAlign': 'left', 'fontSize': '14px'},
        style_data_conditional=[
            {'if': {'filter_query': '{status} = "Running ✅"'}, 'backgroundColor': '#e8f5e9'},
            {'if': {'filter_query': '{status} = "Not Ready ❌"'}, 'backgroundColor': '#ffebee'}
        ],
        markdown_options={"html": True}
    ), button_styles, env_selected

@app.callback(
    Output('logs-container', 'children'),
    Input('table', 'selected_rows'),
    State('table', 'data'),
    State('selected-env', 'children')
)
def display_logs(selected_rows, rows, env):
    if not selected_rows:
        return 'Select a deployment from the table to view logs.'

    deployment_name = rows[selected_rows[0]].get('name')
    response = requests.get(f"{API_URL}/{env}-logs/{deployment_name}")
    return response.json().get('logs', 'No logs available.') if response.status_code == 200 else 'Failed to fetch logs.'

if __name__ == '__main__':
    app.run(debug=True, port=8050)
