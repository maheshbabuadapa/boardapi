from flask import Flask, jsonify
import subprocess
import ssl
import socket
from datetime import datetime

app = Flask(__name__)

CLUSTERS = {
    "dev": {
        "url": "https://dev-openshift-cluster-url:6443",
        "username": "dev-username",
        "password": "dev-password",
        "namespace": "dev-namespace"
    },
    "sit": {
        "url": "https://sit-openshift-cluster-url:6443",
        "username": "sit-username",
        "password": "sit-password",
        "namespace": "sit-namespace"
    },
    "uat": {
        "url": "https://uat-openshift-cluster-url:6443",
        "username": "uat-username",
        "password": "uat-password",
        "namespace": "uat-namespace"
    },
    "preprod": {
        "url": "https://preprod-openshift-cluster-url:6443",
        "username": "preprod-username",
        "password": "preprod-password",
        "namespace": "preprod-namespace"
    }
}


def get_ssl_expiry(domain):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                expiry_date = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                return expiry_date.strftime('%Y-%m-%d')
    except Exception as e:
        return f"Error: {str(e)}"


def login_to_cluster(cluster):
    cluster_info = CLUSTERS[cluster]
    login_cmd = [
        "oc", "login", cluster_info["url"],
        "-u", cluster_info["username"],
        "-p", cluster_info["password"],
        "--insecure-skip-tls-verify=true"
    ]
    result = subprocess.run(login_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"Login failed: {result.stderr}")
    else:
        print(f"Login successful for {cluster}")


def get_deployments_info(cluster):
    login_to_cluster(cluster)
    namespace = CLUSTERS[cluster]["namespace"]

    deploy_cmd = [
        "oc", "get", "deployments", "-n", namespace, "-o",
        "jsonpath={range .items[*]}{'{'}\"name\":\"{.metadata.name}\",\"image\":\"{.spec.template.spec.containers[*].image}\",\"ready\":\"{.status.readyReplicas}/{.status.replicas}\"{'}'}{'\\n'}{end}"
    ]
    deploy_result = subprocess.run(deploy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    deployments = []
    if deploy_result.returncode == 0:
        for line in deploy_result.stdout.strip().split('\n'):
            deployments.append(eval(line))
    else:
        print(f"Error getting deployments: {deploy_result.stderr}")
        return []

    route_cmd = [
        "oc", "get", "route", "-n", namespace, "-o",
        "jsonpath={range .items[*]}{.metadata.name}{'|'}{.spec.host}{'|'}{.spec.tls.termination}{'\\n'}{end}"
    ]
    route_result = subprocess.run(route_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    route_map = {}
    if route_result.returncode == 0:
        for line in route_result.stdout.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 2:
                name, host = parts[0], parts[1]
                scheme = "https" if len(parts) == 3 and parts[2] else "http"
                route_map[name] = (host, scheme)
    else:
        print(f"Error getting routes: {route_result.stderr}")

    for deployment in deployments:
        app_name = deployment["name"]
        route_info = route_map.get(app_name)
        if route_info:
            host, scheme = route_info
            deployment["route"] = f"{scheme}://{host}"
            if scheme == "https":
                deployment["ssl_expiry"] = get_ssl_expiry(host)
            else:
                deployment["ssl_expiry"] = "Not HTTPS"
        else:
            deployment["route"] = "N/A"
            deployment["ssl_expiry"] = "No route found"

    return deployments


@app.route('/<env>')
def deployments_info(env):
    if env not in CLUSTERS:
        return jsonify({"error": "Environment not found"}), 404
    deployments = get_deployments_info(env)
    return jsonify(deployments)


@app.route('/<env>-logs/<deployment_name>')
def deployment_logs(env, deployment_name):
    if env not in CLUSTERS:
        return jsonify({"error": "Environment not found"}), 404
    logs = get_all_pods_logs(env, deployment_name)
    return jsonify({"deployment": deployment_name, "logs": logs})


def get_all_pods_logs(cluster, deployment_name, timeout=30):
    try:
        login_to_cluster(cluster)
        namespace = CLUSTERS[cluster]["namespace"]

        selector_cmd = [
            "oc", "get", "deployment", deployment_name, "-n", namespace,
            "-o", "jsonpath={.spec.selector.matchLabels}"
        ]
        selector_result = subprocess.run(selector_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if selector_result.returncode != 0:
            return f"Error fetching selector: {selector_result.stderr}"

        import json
        match_labels = eval(selector_result.stdout.strip())
        label_selector = ",".join([f"{k}={v}" for k, v in match_labels.items()])

        get_pods_cmd = [
            "oc", "get", "pods", "-n", namespace, "-l", label_selector,
            "-o", "jsonpath={.items[*].metadata.name}"
        ]
        pod_result = subprocess.run(get_pods_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if pod_result.returncode != 0:
            return f"Error fetching pod names: {pod_result.stderr}"

        pod_names = pod_result.stdout.strip().split()
        if not pod_names:
            return f"No pods found for deployment '{deployment_name}' in namespace '{namespace}'."

        logs = {}
        for pod_name in pod_names:
            logs_cmd = ["oc", "logs", pod_name, "-n", namespace]
            logs_result = subprocess.run(logs_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            logs[pod_name] = logs_result.stdout if logs_result.returncode == 0 else f"Error fetching logs: {logs_result.stderr}"

        return logs

    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:
        return f"Unexpected error: {str(e)}"


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)