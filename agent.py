import sys
from kubernetes import client, config

# --- Configuration ---
EXPECTED_CLUSTER_NAME = "staging"
KUBECONFIG_PATH = "~/.kube_tool/staging-eu"

class KubernetesDiagnosticAgent:
    def __init__(self, namespace, app_label, country_label, fleet_label=None):
        self.namespace = namespace
        self.app_label = app_label
        self.country_label = country_label
        self.fleet_label = fleet_label
        self.v1_api = None
        self.pods = []

    def _connect_and_validate(self):
        """Establishes connection to the Kubernetes cluster and validates the context."""
        try:
            contexts, active_context = config.list_kube_config_contexts(config_file=KUBECONFIG_PATH)
            if not active_context:
                raise ConnectionError("No active context found in kubeconfig.")

            current_cluster_name = active_context['context']['cluster']
            if current_cluster_name != EXPECTED_CLUSTER_NAME:
                raise ConnectionError(
                    f"This script is configured to run only against the '{EXPECTED_CLUSTER_NAME}' cluster, "
                    f"but the current context is '{current_cluster_name}'. Aborting."
                )

            print(f"Successfully validated connection to '{current_cluster_name}' cluster.")
            config.load_kube_config(config_file=KUBECONFIG_PATH, context=active_context['name'])
            self.v1_api = client.CoreV1Api()
        except FileNotFoundError:
            raise ConnectionError(f"Kubeconfig file not found at '{KUBECONFIG_PATH}'")
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
        for pod in self.pods:
            is_healthy, reason = self._is_pod_healthy(pod)
            if is_healthy:
                print(f"- [HEALTHY] {pod.metadata.name}")
            else:
                print(f"- [UNHEALTHY] {pod.metadata.name} - Reason: {reason}")
                diagnostics = self._get_pod_diagnostics(pod)
                indented_events = diagnostics['events'].replace('\n', '\n    ')
                indented_logs = diagnostics['logs'].replace('\n', '\n    ')
                print("  \n  Recent Events:")
                print(f"    {indented_events}")
                print("  \n  Logs from Crashed Containers:")
                print(f"    {indented_logs}")
                
                diagnosis, recommendation = self._generate_diagnosis(reason, diagnostics['events'], diagnostics['logs'])
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
                        tail_lines=50
                    )
                    log_messages.append(f"--- Logs for container '{cs.name}' ---\n{logs}")
                except client.ApiException:
                    log_messages.append(f"Could not retrieve logs for previous instance of container '{cs.name}'.")
        diagnostics["logs"] = "\n".join(log_messages) if log_messages else "No logs from previously terminated containers found."

        return diagnostics

    def _generate_diagnosis(self, unhealthy_reason, pod_events, container_logs):
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

        if "CrashLoopBackOff" in unhealthy_reason:
            return ("The container is crashing with an un-recognized application error.",
                    "Please examine the container logs closely to identify the root cause of the stack trace or error message.")

        return ("The pod is in an unhealthy state.", "Please review the pod events and container statuses for more specific clues.")
