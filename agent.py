import sys
import os
from kubernetes import client, config
from dotenv import load_dotenv
import google.generativeai as genai
from node_collector import NodeCollector

# --- LLM Configuration ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in .env file.", file=sys.stderr)
    sys.exit(1)
genai.configure(api_key=GEMINI_API_KEY)


class KubernetesDiagnosticAgent:
    def __init__(self, namespace, app_label, country_label, fleet_label=None, cluster_name="staging-eu"):
        self.namespace = namespace
        self.app_label = app_label
        self.country_label = country_label
        self.fleet_label = fleet_label
        self.cluster_name = cluster_name
        self.v1_api = None
        self.pods = []
        self.llm_model = genai.GenerativeModel('gemini-2.0-flash')
        # NodeCollector needs v1_api, which is initialized in _connect_and_validate
        # So, we'll initialize it after v1_api is ready.
        self.node_collector = None

    def _connect_and_validate(self):
        """Establishes connection to the Kubernetes cluster and validates the context."""
        try:
            kubeconfig_path = os.path.expanduser(f"~/.kube_tool/{self.cluster_name}")
            contexts, active_context = config.list_kube_config_contexts(config_file=kubeconfig_path)
            if not active_context:
                raise ConnectionError("No active context found in kubeconfig.")

            current_cluster_name = active_context['context']['cluster']

            print(f"Successfully validated connection to '{current_cluster_name}' cluster.")
            config.load_kube_config(config_file=kubeconfig_path, context=active_context['name'])
            self.v1_api = client.CoreV1Api()
            self.node_collector = NodeCollector(self.v1_api) # Initialize NodeCollector here
        except FileNotFoundError:
            raise ConnectionError(f"Kubeconfig file not found at '{kubeconfig_path}'")
        except Exception as e:
            raise ConnectionError(f"An unexpected error occurred during connection: {e}")

    def discover_pods(self):
        """Discovers pods based on the configured labels."""
        labels = {"app": self.app_label, "country": self.country_label}
        if self.fleet_label:
            labels["fleet"] = self.fleet_label
        
        label_selector = ",".join([f"{key}={value}" for key, value in labels.items()])
        print(f"\nSearching for pods in namespace '{self.namespace}' with label selector '{label_selector}'...")
        try:
            pod_list = self.v1_api.list_namespaced_pod(self.namespace, label_selector=label_selector)
            self.pods = pod_list.items
            if not self.pods:
                print("No matching pods found.")
        except client.ApiException as e:
            print(f"Error discovering pods: {e}", file=sys.stderr)
            self.pods = []

    def analyze_pods(self):
        """Analyzes the health of discovered pods and prints diagnostics."""
        print(f"Found {len(self.pods)} matching pods. Analyzing health...\n")

        node_diagnostics = self.node_collector.get_node_diagnostics()
        

        for pod in self.pods:
            is_healthy, reason = self._is_pod_healthy(pod)
            if is_healthy:
                print(f"- [HEALTHY] {pod.metadata.name}")
            else:
                print(f"- [UNHEALTHY] {pod.metadata.name} - Reason: {reason}")
                pod_diagnostics = self._get_pod_diagnostics(pod)
                
                diagnosis, recommendation = self._generate_diagnosis(pod, reason, pod_diagnostics['events'], pod_diagnostics['logs'], node_diagnostics)
                print("\n  ==================== DIAGNOSIS ====================")
                print(f"  Diagnosis:      {diagnosis}")
                print(f"  Recommendation: {recommendation}")
                print("  =================================================\n")

    def run(self):
        """Runs the complete diagnostic process."""
        try:
            self._connect_and_validate()
            self.discover_pods()
            if self.pods:
                self.analyze_pods()
        except ConnectionError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def _is_pod_healthy(self, pod):
        if pod.status.phase in ['Failed', 'Unknown']:
            return False, f"Pod is in a non-running phase: {pod.status.phase}"
        if pod.status.phase == 'Pending':
            return False, "Pod is stuck in Pending phase."

        if not pod.status.container_statuses:
            return False, "Pod has no container statuses, may still be initializing."

        all_containers_ready = True
        for cs in pod.status.container_statuses:
            if cs.state.waiting and cs.state.waiting.reason in ['CrashLoopBackOff', 'ImagePullBackOff', 'Error']:
                return False, f"Container '{cs.name}' is in a waiting state with reason: {cs.state.waiting.reason}"
            if not cs.ready:
                all_containers_ready = False

        if not all_containers_ready:
            return False, "Not all containers in the pod are ready."

        return True, "Healthy"

    def _get_pod_diagnostics(self, pod):
        diagnostics = {"events": "", "logs": ""}
        try:
            event_list = self.v1_api.list_namespaced_event(
                namespace=pod.metadata.namespace,
                field_selector=f"involvedObject.name={pod.metadata.name}"
            )
            event_messages = [f"- {e.last_timestamp} [{e.type}] {e.reason}: {e.message}" for e in event_list.items]
            diagnostics["events"] = "\n".join(event_messages) if event_messages else "No recent events found."
        except client.ApiException as e:
            diagnostics["events"] = f"Could not retrieve events: {e}"

        log_messages = []
        for cs in pod.status.container_statuses:
            if cs.last_state and cs.last_state.terminated:
                try:
                    logs = self.v1_api.read_namespaced_pod_log(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        container=cs.name,
                        previous=True,
                        
                    )
                    log_messages.append(f"--- Logs for container '{cs.name}' ---\n{logs}")
                except client.ApiException:
                    log_messages.append(f"Could not retrieve logs for previous instance of container '{cs.name}'.")
        diagnostics["logs"] = "\n".join(log_messages) if log_messages else "No logs from previously terminated containers found."

        return diagnostics

    def _get_llm_diagnosis(self, pod, reason, pod_events, container_logs, node_diagnostics):
        """Sends diagnostic data to an LLM for analysis."""
        print("  Escalating to LLM for advanced analysis...")
        
        container_statuses = ""
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                container_statuses += f"- Container: {cs.name}, Ready: {cs.ready}, State: {cs.state}\n"

        node_info_str = ""
        for node in node_diagnostics["nodes"]:
            node_info_str += f"- Node: {node['name']}, Status: {node['status']}, Conditions: {node['conditions']}, Taints: {node['taints']}\n"
        
        prompt = f"""
You are an expert Kubernetes reliability engineer. Your task is to analyze the following diagnostic data from an unhealthy pod and determine the most likely root cause.

**Pod Details:**
- Name: {pod.metadata.name}
- Namespace: {pod.metadata.namespace}
- Status: {pod.status.phase}
- Reason for Unhealthiness: {reason}
- Container Statuses: 
{container_statuses}

**Associated Pod Events:**
```
{pod_events}
```

**Crashed Container Logs (from previous instance):**
```
{container_logs}
```

**Cluster Node Information:**
```
{node_info_str}
```

**Recent Node Events:**
```
{node_diagnostics["events"]}
```

**Analysis Request:**
Based on the events and logs provided, what is the most likely root cause of this pod failure? Please provide a concise, one-paragraph explanation. Then, provide a one-sentence recommendation for how to fix it. Format the output as:\nDiagnosis: [Your one-paragraph diagnosis]\nRecommendation: [Your one-sentence recommendation]\n"""
        try:
            response = self.llm_model.generate_content(prompt)
            # Clean up the response text
            cleaned_text = response.text.replace("Diagnosis: ", "").replace("Recommendation: ", "\nRecommendation: ")
            parts = cleaned_text.split("\nRecommendation:")
            diagnosis = parts[0].strip()
            recommendation = parts[1].strip() if len(parts) > 1 else "No specific recommendation provided."
            return (diagnosis, recommendation)
        except Exception as e:
            return (f"LLM analysis failed: {e}", "Could not get a recommendation from the LLM.")


    def _get_rule_based_diagnosis(self, unhealthy_reason, pod_events, container_logs):
        if "OOMKilled" in unhealthy_reason:
            return ("The container was terminated because it exceeded its memory limit.",
                    "Increase the memory limit for this pod in your deployment's resource requests/limits.")
        if "ImagePullBackOff" in unhealthy_reason:
            return ("Kubernetes failed to pull the container image.",
                    "Check that the image name and tag are correct and that the cluster has credentials to pull from the registry.")

        if "FailedScheduling" in pod_events:
            return ("The pod could not be scheduled onto a node.",
                    "This is often due to insufficient resources (CPU, memory) or node taints. Check `kubectl describe node`.")
        if "FailedMount" in pod_events:
            return ("The pod failed to mount a required volume.",
                    "Verify that the volume exists in the namespace and is correctly named in the pod definition.")

        if "connection refused" in container_logs.lower():
            return ("The application is crashing because it cannot connect to another service.",
                    "Verify that the upstream service (e.g., database, API) is running and accessible.")
        if "file not found" in container_logs.lower() or "no such file or directory" in container_logs.lower():
            return ("The application is crashing because a required file is missing.",
                    "Check that all necessary configuration files or scripts are correctly mounted.")
        if "permission denied" in container_logs.lower():
            return ("The application is crashing due to a file system permission error.",
                    "Check the user/group the container is running as and ensure it has correct permissions.")
        
        return None, None # No rule-based diagnosis found

    def _generate_diagnosis(self, pod, unhealthy_reason, pod_events, container_logs, node_diagnostics):
        diagnosis, recommendation = self._get_rule_based_diagnosis(unhealthy_reason, pod_events, container_logs)
        if diagnosis:
            return diagnosis, recommendation
        
        # Fallback to LLM
        return self._get_llm_diagnosis(pod, unhealthy_reason, pod_events, container_logs, node_diagnostics)
