# Kubernetes Diagnostic Agent

This project provides a read-only, local diagnostic tool that connects to a Kubernetes cluster to identify and analyze unhealthy pods based on a set of labels. The agent first collects forensic data about the pod and its node, including events, logs, and node status. It then uses a combination of rule-based analysis and a Large Language Model (LLM) to diagnose the root cause and suggest a solution.

## Architecture

The project is split into two files:

- `agent.py`: A reusable Python library containing the `KubernetesDiagnosticAgent` class, which encapsulates all the diagnostic logic.
- `main.py`: The executable entry point for the tool. It handles command-line argument parsing and uses the `KubernetesDiagnosticAgent` class to run the diagnostics.
- `node_collector.py`: A module responsible for collecting node-level information and events from the Kubernetes cluster.

## Features

- **Flexible Pod Selection:** Filters pods based on `app` (required), `country` (required), and `fleet` (optional) labels.
- **Health Analysis:** Automatically determines if a pod is healthy or unhealthy by checking its status and the state of its containers (e.g., `CrashLoopBackOff`, `ImagePullBackOff`).
- **Forensic Data Collection:** For any unhealthy pod, it automatically gathers:
    - Recent pod-level events.
    - Logs from any previously crashed containers.
    - **Node Information:** Details about the cluster nodes, including their status, conditions (e.g., `MemoryPressure`, `DiskPressure`), allocatable/capacity resources, and taints.
    - **Node Events:** Recent events related to nodes (e.g., `NodeNotReady`, `NodeLost`).
    This data is used internally for analysis and is not printed in full to the console.
- **Automated Diagnosis (Rule-Based & LLM-Powered):**
    - Provides a concise, high-level diagnosis and a recommended next step based on common failure patterns.
    - For complex or ambiguous errors, it escalates to a Large Language Model (LLM) (currently `gemini-2.0-flash`) to provide a more detailed analysis and recommendation, leveraging both pod and node-level forensic data.
- **Safety First:**
    - The agent is **strictly read-only**.
    - It includes a safety check to ensure it only connects to the cluster name specified in its configuration.

## Prerequisites

- Python 3
- `pip` for Python package installation
- Access to a Kubernetes cluster with a valid `kubeconfig` file.
- A Google Gemini API key.

## Installation

1.  **Clone the repository or download the `agent.py`, `main.py`, `node_collector.py`, `requirements.txt`, and `.env` files.**

2.  **Install the required Python packages:**

    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Before running, you must configure the following:

- **`GEMINI_API_KEY`**: Obtain a Google Gemini API key and add it to the `.env` file in the project root. This file is excluded from version control for security.

    ```
    GEMINI_API_KEY='YOUR_API_KEY_HERE'
    ```

- **`EXPECTED_CLUSTER_NAME`**: A critical safety feature. The script will abort if the active context in your `kubeconfig` does not match this name. **Default:** `"staging"`.
- **`KUBECONFIG_PATH`**: The path to your `kubeconfig` file. **Default:** `"~/.kube_tool/staging-eu"`.

These last two variables are configured at the top of the `agent.py` script:

**Example Configuration in `agent.py`:**
```python
# --- Configuration ---
EXPECTED_CLUSTER_NAME = "staging"
KUBECONFIG_PATH = "~/.kube_tool/staging-eu"
```

## How to Run

Execute the `main.py` script from your terminal, providing the required and optional arguments.

### Arguments

- `--app` (required): The value for the `app` label.
- `--country` (required): The value for the `country` label.
- `--fleet` (optional): The value for the `fleet` label.
- `--namespace` (optional): The Kubernetes namespace to search in. Defaults to `default`.

### Example Usage

**1. Basic search for unhealthy pods:**

```bash
python3 main.py --app dashboard --country kr2 --namespace hurrier
```

**2. Search including the optional `fleet` label:**

```bash
python3 main.py --app dashboard --country kr2 --fleet api --namespace hurrier
```