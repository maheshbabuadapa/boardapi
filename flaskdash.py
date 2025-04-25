import dash
from dash import Dash, html, dcc, dash_table, Input, Output, State
import requests
import pandas as pd

API_URL = "http://localhost:5000"  # Flask backend URL

app = Dash(__name__, suppress_callback_exceptions=True)

app.layout = html.Div(style={'padding': '20px', 'fontFamily': 'Arial'}, children=[
    html.H2('OpenShift Deployments Dashboard', style={'color': '#007bff'}),

    html.Div([
        html.Label('Select Environment:', style={'font-weight': 'bold'}),
        dcc.Dropdown(
            id='env-dropdown',
            options=[
                {'label': 'DEV', 'value': 'dev'},
                {'label': 'SIT', 'value': 'sit'},
                {'label': 'UAT', 'value': 'uat'},
                {'label': 'PREPROD', 'value': 'preprod'}
            ],
            value='dev',
            clearable=False,
            style={'width': '200px'}
        ),
    ], style={'marginBottom': '20px'}),

    html.Button('Load Deployments', id='load-btn', n_clicks=0, style={
        'backgroundColor': '#007bff', 'color': 'white', 'border': 'none', 'padding': '10px', 'cursor': 'pointer'
    }),

    html.Div(id='deployments-table', style={'marginTop': '30px'}),

    html.H3('Pod Logs:', style={'marginTop': '40px'}),
    html.Div(id='logs-container', style={
        'whiteSpace': 'pre-wrap',
        'backgroundColor': '#f8f9fa',
        'padding': '10px',
        'borderRadius': '5px',
        'height': '400px',
        'overflowY': 'scroll'
    })
])

@app.callback(
    Output('deployments-table', 'children'),
    Input('load-btn', 'n_clicks'),
    State('env-dropdown', 'value')
)
def update_deployments(n_clicks, env):
    if n_clicks == 0:
        return ""

    response = requests.get(f"{API_URL}/{env}")
    if response.status_code != 200:
        return html.Div('Failed to fetch deployments', style={'color': 'red'})

    deployments = response.json()

    # Enhance data by adding status column
    for dep in deployments:
        ready = dep.get("ready", "")
        try:
            ready_replicas, total_replicas = map(int, ready.split('/'))
            if ready_replicas == total_replicas and total_replicas > 0:
                dep["status"] = "Running ✅"
            else:
                dep["status"] = "Not Ready ❌"
        except:
            dep["status"] = "Unknown ⚠️"
        dep.pop("ready", None)  # Remove 'ready' column

    df = pd.DataFrame(deployments)

    # Format route column to be clickable links
    if 'route' in df.columns:
        df['route'] = df['route'].apply(lambda x: f"[Open Route]({x})" if x else "No Route")

    # Define style based on status
    style_data_conditional = [
        {
            'if': {
                'filter_query': '{status} = "Running ✅"',
                'column_id': 'status'
            },
            'backgroundColor': '#d4edda',
            'color': '#155724',
            'fontWeight': 'bold'
        },
        {
            'if': {
                'filter_query': '{status} = "Not Ready ❌"',
                'column_id': 'status'
            },
            'backgroundColor': '#f8d7da',
            'color': '#721c24',
            'fontWeight': 'bold'
        }
    ]

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
        style_table={'overflowX': 'auto'},
        style_header={'backgroundColor': '#007bff', 'color': 'white', 'fontWeight': 'bold'},
        style_cell={'padding': '10px', 'textAlign': 'left'},
        style_data_conditional=style_data_conditional,
        markdown_options={"html": True},
    )

@app.callback(
    Output('logs-container', 'children'),
    Input('table', 'selected_rows'),
    State('table', 'data'),
    State('env-dropdown', 'value')
)
def display_logs(selected_rows, rows, env):
    if selected_rows is None or len(selected_rows) == 0:
        return 'Select a deployment to view logs.'

    deployment_name = rows[selected_rows[0]]['name']
    response = requests.get(f"{API_URL}/{env}-logs/{deployment_name}")

    if response.status_code != 200:
        return 'Failed to fetch logs.'

    logs = response.json().get('logs', 'No logs available.')

    return logs

if __name__ == '__main__':
    app.run(debug=True, port=8050)
