
# devops_sre_dashboard.py
import streamlit as st
import json
import os
from urllib.parse import urlparse

st.set_page_config(page_title="DevOps & SRE Journey Dashboard", layout="wide")

# --- Data persistence functions ---
DATA_FILE = os.path.join(os.path.dirname(__file__), "dashboard_progress.json")

# Remote S3/HTTP location for the progress JSON. By default uses the public
# S3 HTTPS URL you provided (read-only). You can override with env var
# DASHBOARD_S3_LOCATION to point to a different location. If you set an
# s3:// URL and provide AWS credentials (env vars or instance role), the
# app will attempt to upload when saving.
S3_LOCATION = os.environ.get("DASHBOARD_S3_LOCATION", "https://nasir473-resume.s3.ap-south-1.amazonaws.com/dev-ops-dashboard/dashboard_progress.json")

# Lazy boto3 client (created only when needed)
_s3_client = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        try:
            import boto3
        except Exception:
            raise
        _s3_client = boto3.client('s3')
    return _s3_client

def is_http_url(url: str) -> bool:
    return url.startswith('http://') or url.startswith('https://')

def is_s3_url(url: str) -> bool:
    return url.startswith('s3://')

def parse_s3_url(s3_url: str):
    # returns (bucket, key)
    if s3_url.startswith('s3://'):
        without = s3_url[len('s3://'):]
        parts = without.split('/', 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ''
        return bucket, key
    raise ValueError('Invalid s3 url')

def load_progress():
    """Load progress from local file"""
    # If no remote configured, fall back to local (existing behaviour)
    if not S3_LOCATION:
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return {}
        return {}

    # If remote is HTTP(S) - public read
    if is_http_url(S3_LOCATION):
        try:
            import requests
            resp = requests.get(S3_LOCATION, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # show a warning in the UI but fallback to local file for offline use
            try:
                st.warning(f"Could not load remote JSON at {S3_LOCATION}: {e}. Falling back to local file.")
            except Exception:
                pass
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r') as f:
                        return json.load(f)
                except Exception:
                    return {}
            return {}

    # If remote is s3:// - use boto3 (requires credentials)
    if is_s3_url(S3_LOCATION):
        try:
            bucket, key = parse_s3_url(S3_LOCATION)
            s3 = get_s3_client()
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj['Body'].read().decode('utf-8')
            return json.loads(body)
        except Exception as e:
            try:
                st.warning(f"Could not load remote S3 JSON {S3_LOCATION}: {e}. Falling back to local file.")
            except Exception:
                pass
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r') as f:
                        return json.load(f)
                except Exception:
                    return {}
            return {}

    # Unknown scheme - fallback
    return {}

def save_progress(data):
    """Save progress to local file"""
    # Always maintain a local copy as a backup
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        try:
            st.warning(f"Could not write local backup: {e}")
        except Exception:
            pass

    # If S3_LOCATION empty - nothing else to do
    if not S3_LOCATION:
        return

    # If S3_LOCATION is HTTP(S) (public S3 url) we cannot upload directly
    if is_http_url(S3_LOCATION):
        try:
            st.info("Remote location is HTTP(S) (public). Local copy saved. To enable remote uploads, set DASHBOARD_S3_LOCATION to an s3:// URL and provide AWS credentials.")
        except Exception:
            pass
        return

    # If S3_LOCATION is s3:// we will attempt to upload using boto3
    if is_s3_url(S3_LOCATION):
        try:
            bucket, key = parse_s3_url(S3_LOCATION)
            s3 = get_s3_client()
            s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(data).encode('utf-8'), ContentType='application/json')
            try:
                st.success("Progress saved to S3")
            except Exception:
                pass
        except Exception as e:
            try:
                st.error(f"Failed to save to S3: {e}")
            except Exception:
                pass
        return

# Initialize session state
if 'progress' not in st.session_state:
    st.session_state.progress = load_progress()
if 'notes' not in st.session_state:
    notes_data = st.session_state.progress.get('notes', {})
    st.session_state.notes = {
        'to_learn': notes_data.get('to_learn', ''),
        'in_progress': notes_data.get('in_progress', ''),
        'completed': notes_data.get('completed', '')
    }
if 'show_reset_confirmation' not in st.session_state:
    st.session_state.show_reset_confirmation = False

st.title("🚀 DevOps & SRE Journey Dashboard")
st.write("Track your learning progress across DevOps and SRE domains — your progress is automatically saved!")

# Add CSS for better navigation buttons
st.markdown("""
<style>
.nav-button {
    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
    border: none;
    color: white;
    padding: 15px 20px;
    text-align: center;
    text-decoration: none;
    display: inline-block;
    font-size: 16px;
    margin: 4px 2px;
    cursor: pointer;
    border-radius: 12px;
    width: 100%;
    transition: all 0.3s;
}
.nav-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}
</style>
""", unsafe_allow_html=True)

# --- Helper for calculating section progress ---
def section_progress(items):
    return sum(items.values()) / len(items) * 100 if items else 0

def persistent_checkbox(label, key):
    """Create a checkbox that remembers its state"""
    value = st.checkbox(label, value=st.session_state.progress.get(key, False), key=key)
    st.session_state.progress[key] = value
    return value

def create_subtask_section(main_task, subtasks, section_key):
    """Create an expandable section with subtasks"""
    with st.expander(f"📋 {main_task}", expanded=False):
        subtask_progress = {}
        for subtask_key, subtask_name in subtasks.items():
            full_key = f"{section_key}_{subtask_key}"
            subtask_progress[subtask_key] = persistent_checkbox(subtask_name, full_key)
        
        # Calculate and display subtask progress
        if subtasks:
            progress = sum(subtask_progress.values()) / len(subtask_progress) * 100
            st.progress(progress / 100)
            st.caption(f"Subtask Progress: {progress:.0f}%")
        
        return subtask_progress

def calculate_section_progress():
    """Calculate progress for all sections based on current state"""
    # Define all subtask structures
    sections_data = {
        'foundations': {
            'linux': ["basic_commands", "file_operations", "permissions", "text_processing", "process_mgmt", "system_info", "package_mgmt", "user_mgmt", "cron_jobs", "log_analysis"],
            'scripting': ["bash_basics", "bash_advanced", "python_basics", "python_modules", "automation_scripts", "error_handling", "script_deployment", "config_management"],
            'docker': ["docker_concepts", "dockerfile", "docker_commands", "volumes_networks", "docker_compose", "registry_mgmt", "security", "optimization"],
            'yaml_json': ["yaml_syntax", "json_syntax", "data_validation", "templating", "config_files", "api_responses"],
            'networking': ["osi_model", "ip_subnetting", "dns_concepts", "load_balancing", "firewalls", "network_tools", "ssl_tls", "vpn_concepts"],
            'sdlc': ["sdlc_phases", "agile_scrum", "waterfall", "devops_integration", "quality_assurance", "deployment_strategies"]
        },
        'cicd': {
            'git': ["git_basics", "branching", "git_workflow", "conflict_resolution", "git_hooks", "github_features", "code_review", "git_advanced"],
            'jenkins': ["jenkins_setup", "pipeline_syntax", "build_jobs", "pipeline_stages", "jenkins_plugins", "build_triggers", "artifacts", "jenkins_security"],
            'github_actions': ["workflow_syntax", "actions_marketplace", "ci_workflows", "cd_workflows", "secrets_management", "matrix_builds", "custom_actions", "workflow_optimization"],
            'testing': ["unit_testing", "integration_testing", "e2e_testing", "test_automation", "code_coverage", "performance_testing", "security_testing", "test_reporting"],
            'deployment': ["deployment_strategies", "rollback_mechanisms", "env_management", "config_management", "release_automation", "deployment_tools", "database_migrations", "monitoring_deployment"]
        },
        'cloud': {
            'aws': ["aws_basics", "ec2", "s3", "iam", "vpc", "rds", "cloudwatch", "lambda", "elb", "aws_cli"],
            'terraform': ["terraform_basics", "terraform_state", "terraform_modules", "terraform_variables", "terraform_provisioners", "terraform_workspaces", "terraform_import", "terraform_best_practices"],
            'k8s': ["k8s_architecture", "pods", "deployments", "services", "configmaps_secrets", "ingress", "volumes", "rbac", "kubectl", "troubleshooting"],
            'helm': ["helm_basics", "helm_templates", "helm_hooks", "kustomize_basics", "kustomize_patches", "package_management", "helm_security"]
        },
        'monitoring': {
            'prometheus': ["prometheus_basics", "metrics_collection", "promql", "alerting_rules", "grafana_dashboards", "grafana_alerts", "service_discovery", "monitoring_best_practices"],
            'elk': ["elasticsearch", "logstash", "kibana", "filebeat", "fluentd", "log_parsing", "index_management", "security_logging"],
            'cloudwatch': ["cloudwatch_metrics", "cloudwatch_logs", "cloudwatch_alarms", "cloudwatch_dashboards", "datadog_basics", "datadog_dashboards", "datadog_alerts", "apm_tracing"],
            'incident': ["incident_response", "on_call_practices", "escalation_procedures", "incident_tools", "post_incident", "runbooks", "communication", "metrics_tracking"]
        },
        'sre': {
            'slo': ["sli_definition", "slo_setting", "sla_management", "error_budget", "slo_monitoring", "slo_reporting"],
            'budget': ["error_budget_concept", "toil_identification", "automation_prioritization", "capacity_planning", "reliability_engineering", "toil_reduction"],
            'rca': ["incident_classification", "incident_response_process", "rca_methodology", "blameless_postmortem", "action_items", "incident_prevention", "communication_protocols", "learning_culture"],
            'automation': ["infrastructure_automation", "deployment_automation", "testing_automation", "monitoring_automation", "self_healing", "auto_scaling", "pipeline_optimization", "automation_testing"],
            'chaos': ["chaos_principles", "chaos_tools", "failure_injection", "blast_radius", "chaos_experiments", "resilience_testing", "gamedays", "chaos_automation"]
        }
    }
    
    # Calculate progress for each main section
    section_progress = {}
    section_totals = {}
    section_counts = {}
    
    for main_section, subsections in sections_data.items():
        total_completed = 0
        total_tasks = 0
        
        for subsection_key, tasks in subsections.items():
            for task in tasks:
                full_key = f"{subsection_key}_{task}"
                if st.session_state.progress.get(full_key, False):
                    total_completed += 1
                total_tasks += 1
        
        section_totals[main_section] = total_completed
        section_counts[main_section] = total_tasks
        section_progress[main_section] = (total_completed / total_tasks * 100) if total_tasks > 0 else 0
    
    return section_progress, section_totals, section_counts

# Calculate progress for overview
progress_data, totals_data, counts_data = calculate_section_progress()

# --- Overall Progress Section (Moved to Top) ---
st.markdown("---")
st.subheader("🏁 Overall Progress Overview")

f_progress = progress_data.get('foundations', 0)
cicd_progress = progress_data.get('cicd', 0)
cloud_progress = progress_data.get('cloud', 0)
mon_progress = progress_data.get('monitoring', 0)
sre_progress = progress_data.get('sre', 0)

overall = (f_progress + cicd_progress + cloud_progress + mon_progress + sre_progress) / 5
st.progress(overall / 100)

# Create clickable navigation links using markdown
st.markdown("### 📋 Quick Navigation - Click to jump to sections:")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"""
    <a href="#foundations" style="text-decoration: none;">
        <div class="nav-button">
            🧩 Foundations<br>
            <strong>{f_progress:.1f}%</strong>
        </div>
    </a>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <a href="#cicd" style="text-decoration: none;">
        <div class="nav-button">
            ⚙️ CI/CD & Source Control<br>
            <strong>{cicd_progress:.1f}%</strong>
        </div>
    </a>
    """, unsafe_allow_html=True)
    
with col2:
    st.markdown(f"""
    <a href="#cloud" style="text-decoration: none;">
        <div class="nav-button">
            ☁️ Cloud & IaC<br>
            <strong>{cloud_progress:.1f}%</strong>
        </div>
    </a>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <a href="#monitoring" style="text-decoration: none;">
        <div class="nav-button">
            📊 Monitoring & Observability<br>
            <strong>{mon_progress:.1f}%</strong>
        </div>
    </a>
    """, unsafe_allow_html=True)
    
with col3:
    st.markdown(f"""
    <a href="#sre" style="text-decoration: none;">
        <div class="nav-button">
            🧠 SRE Mindset & Practices<br>
            <strong>{sre_progress:.1f}%</strong>
        </div>
    </a>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <a href="#notes" style="text-decoration: none;">
        <div class="nav-button">
            📋 Notes & Dashboard<br>
            <strong>View Notes</strong>
        </div>
    </a>
    """, unsafe_allow_html=True)

st.success(f"🎯 Your overall DevOps & SRE learning progress: {overall:.1f}%")

# Calculate total completed tasks
total_completed = sum(totals_data.values())
total_tasks = sum(counts_data.values())

if total_tasks > 0:
    st.info(f"📊 Completed: {total_completed}/{total_tasks} tasks ({total_completed/total_tasks*100:.1f}%)")

# --- Section 1: Foundations ---
st.markdown('<div id="foundations"></div>', unsafe_allow_html=True)
st.subheader("🧩 Foundations")

# Linux Fundamentals
linux_subtasks = {
    "basic_commands": "Basic Commands (ls, cd, pwd, mkdir, rmdir)",
    "file_operations": "File Operations (cp, mv, rm, find, grep)",
    "permissions": "File Permissions & Ownership (chmod, chown, chgrp)",
    "text_processing": "Text Processing (cat, head, tail, awk, sed)",
    "process_mgmt": "Process Management (ps, top, kill, jobs, nohup)",
    "system_info": "System Information (df, du, free, uname, lscpu)",
    "package_mgmt": "Package Management (apt, yum, dpkg, rpm)",
    "user_mgmt": "User & Group Management (useradd, usermod, su, sudo)",
    "cron_jobs": "Cron Jobs & Task Scheduling",
    "log_analysis": "Log Files & System Monitoring (/var/log, journalctl)"
}
linux_progress = create_subtask_section("Linux Fundamentals", linux_subtasks, "linux")

# Scripting (Shell/Python)
scripting_subtasks = {
    "bash_basics": "Bash Scripting Basics (variables, loops, conditions)",
    "bash_advanced": "Advanced Bash (functions, arrays, error handling)",
    "python_basics": "Python Basics (syntax, data types, control flow)",
    "python_modules": "Python Modules (os, sys, subprocess, requests)",
    "automation_scripts": "Automation Scripts (file processing, API calls)",
    "error_handling": "Error Handling & Logging",
    "script_deployment": "Script Deployment & Execution",
    "config_management": "Configuration Management with Scripts"
}
scripting_progress = create_subtask_section("Scripting (Shell/Python)", scripting_subtasks, "scripting")

# Containers / Docker Basics
docker_subtasks = {
    "docker_concepts": "Docker Concepts (images, containers, registries)",
    "dockerfile": "Dockerfile Creation & Best Practices",
    "docker_commands": "Docker Commands (run, build, push, pull)",
    "volumes_networks": "Docker Volumes & Networks",
    "docker_compose": "Docker Compose (multi-container apps)",
    "registry_mgmt": "Registry Management (Docker Hub, ECR)",
    "security": "Container Security Best Practices",
    "optimization": "Image Optimization & Layer Management"
}
docker_progress = create_subtask_section("Containers / Docker Basics", docker_subtasks, "docker")

# YAML & JSON
yaml_json_subtasks = {
    "yaml_syntax": "YAML Syntax & Structure",
    "json_syntax": "JSON Syntax & Structure",
    "data_validation": "Data Validation & Schema",
    "templating": "YAML/JSON Templating (Jinja2, Go templates)",
    "config_files": "Configuration Files Management",
    "api_responses": "API Request/Response Handling"
}
yaml_json_progress = create_subtask_section("YAML & JSON", yaml_json_subtasks, "yaml_json")

# Networking Basics
networking_subtasks = {
    "osi_model": "OSI Model & TCP/IP Stack",
    "ip_subnetting": "IP Addressing & Subnetting",
    "dns_concepts": "DNS & Domain Resolution",
    "load_balancing": "Load Balancing Concepts",
    "firewalls": "Firewalls & Security Groups",
    "network_tools": "Network Tools (ping, telnet, netstat, ss)",
    "ssl_tls": "SSL/TLS & Certificate Management",
    "vpn_concepts": "VPN & Network Security"
}
networking_progress = create_subtask_section("Networking Basics", networking_subtasks, "networking")

# SDLC Life Cycle
sdlc_subtasks = {
    "sdlc_phases": "SDLC Phases (Planning, Analysis, Design, Implementation)",
    "agile_scrum": "Agile & Scrum Methodologies",
    "waterfall": "Waterfall Model Understanding",
    "devops_integration": "DevOps Integration in SDLC",
    "quality_assurance": "Quality Assurance & Testing",
    "deployment_strategies": "Deployment Strategies & Release Management"
}
sdlc_progress = create_subtask_section("SDLC Life Cycle", sdlc_subtasks, "sdlc")

# Calculate overall foundations progress
all_foundations_progress = [linux_progress, scripting_progress, docker_progress, yaml_json_progress, networking_progress, sdlc_progress]
foundations_total = sum([sum(section.values()) for section in all_foundations_progress])
foundations_count = sum([len(section) for section in all_foundations_progress])
f_progress = (foundations_total / foundations_count * 100) if foundations_count > 0 else 0

st.progress(f_progress / 100)
st.caption(f"Overall Foundations Progress: {f_progress:.0f}%")

st.divider()

# --- Section 2: CI/CD & Source Control ---
st.markdown('<div id="cicd"></div>', unsafe_allow_html=True)
st.subheader("⚙️ CI/CD & Source Control")

# Git & GitHub
git_subtasks = {
    "git_basics": "Git Basics (init, add, commit, push, pull)",
    "branching": "Branching & Merging Strategies",
    "git_workflow": "Git Workflow (feature branches, PRs)",
    "conflict_resolution": "Merge Conflict Resolution",
    "git_hooks": "Git Hooks & Pre-commit",
    "github_features": "GitHub Features (Issues, Projects, Actions)",
    "code_review": "Code Review Process",
    "git_advanced": "Advanced Git (rebase, squash, cherry-pick)"
}
git_progress = create_subtask_section("Git & GitHub", git_subtasks, "git")

# Jenkins Pipelines
jenkins_subtasks = {
    "jenkins_setup": "Jenkins Installation & Configuration",
    "pipeline_syntax": "Pipeline Syntax (Declarative & Scripted)",
    "build_jobs": "Build Jobs & Freestyle Projects",
    "pipeline_stages": "Pipeline Stages & Steps",
    "jenkins_plugins": "Jenkins Plugins (Git, Docker, AWS)",
    "build_triggers": "Build Triggers & Webhooks",
    "artifacts": "Artifact Management",
    "jenkins_security": "Jenkins Security & Access Control"
}
jenkins_progress = create_subtask_section("Jenkins Pipelines", jenkins_subtasks, "jenkins")

# GitHub Actions
github_actions_subtasks = {
    "workflow_syntax": "Workflow YAML Syntax",
    "actions_marketplace": "GitHub Actions Marketplace",
    "ci_workflows": "CI Workflows (build, test, lint)",
    "cd_workflows": "CD Workflows (deploy, release)",
    "secrets_management": "Secrets & Environment Variables",
    "matrix_builds": "Matrix Builds & Strategy",
    "custom_actions": "Custom Actions Development",
    "workflow_optimization": "Workflow Optimization & Caching"
}
github_actions_progress = create_subtask_section("GitHub Actions", github_actions_subtasks, "github_actions")

# Automated Testing
testing_subtasks = {
    "unit_testing": "Unit Testing Frameworks",
    "integration_testing": "Integration Testing",
    "e2e_testing": "End-to-End Testing",
    "test_automation": "Test Automation in CI/CD",
    "code_coverage": "Code Coverage & Quality Gates",
    "performance_testing": "Performance & Load Testing",
    "security_testing": "Security Testing (SAST, DAST)",
    "test_reporting": "Test Reporting & Metrics"
}
testing_progress = create_subtask_section("Automated Testing", testing_subtasks, "testing")

# Deployment Automation
deployment_subtasks = {
    "deployment_strategies": "Deployment Strategies (Blue-Green, Canary)",
    "rollback_mechanisms": "Rollback Mechanisms",
    "env_management": "Environment Management",
    "config_management": "Configuration Management",
    "release_automation": "Release Automation",
    "deployment_tools": "Deployment Tools (Ansible, Octopus)",
    "database_migrations": "Database Migration Automation",
    "monitoring_deployment": "Deployment Monitoring & Validation"
}
deployment_progress = create_subtask_section("Deployment Automation", deployment_subtasks, "deployment")

# Calculate overall CI/CD progress
all_cicd_progress = [git_progress, jenkins_progress, github_actions_progress, testing_progress, deployment_progress]
cicd_total = sum([sum(section.values()) for section in all_cicd_progress])
cicd_count = sum([len(section) for section in all_cicd_progress])
cicd_progress = (cicd_total / cicd_count * 100) if cicd_count > 0 else 0

st.progress(cicd_progress / 100)
st.caption(f"Overall CI/CD Progress: {cicd_progress:.0f}%")

st.divider()

# --- Section 3: Cloud & Infrastructure as Code (IaC) ---
st.markdown('<div id="cloud"></div>', unsafe_allow_html=True)
st.subheader("☁️ Cloud & Infrastructure as Code (IaC)")

# AWS Fundamentals
aws_subtasks = {
    "aws_basics": "AWS Basics & Global Infrastructure",
    "ec2": "EC2 (Instances, AMIs, Key Pairs, Security Groups)",
    "s3": "S3 (Buckets, Objects, Permissions, Lifecycle)",
    "iam": "IAM (Users, Groups, Roles, Policies)",
    "vpc": "VPC (Subnets, Route Tables, Internet Gateway)",
    "rds": "RDS & Database Services",
    "cloudwatch": "CloudWatch (Metrics, Logs, Alarms)",
    "lambda": "Lambda & Serverless",
    "elb": "Load Balancers (ALB, NLB, CLB)",
    "aws_cli": "AWS CLI & SDK"
}
aws_progress = create_subtask_section("AWS Fundamentals", aws_subtasks, "aws")

# Terraform
terraform_subtasks = {
    "terraform_basics": "Terraform Basics (HCL, Resources, Providers)",
    "terraform_state": "State Management & Backends",
    "terraform_modules": "Modules & Code Organization",
    "terraform_variables": "Variables & Outputs",
    "terraform_provisioners": "Provisioners & Local-exec",
    "terraform_workspaces": "Workspaces & Environment Management",
    "terraform_import": "Import & Data Sources",
    "terraform_best_practices": "Best Practices & Security"
}
terraform_progress = create_subtask_section("Terraform", terraform_subtasks, "terraform")

# Kubernetes
k8s_subtasks = {
    "k8s_architecture": "Kubernetes Architecture & Components",
    "pods": "Pods & Container Management",
    "deployments": "Deployments & ReplicaSets",
    "services": "Services & Networking",
    "configmaps_secrets": "ConfigMaps & Secrets",
    "ingress": "Ingress Controllers & Load Balancing",
    "volumes": "Persistent Volumes & Storage",
    "rbac": "RBAC & Security",
    "kubectl": "kubectl Commands & Management",
    "troubleshooting": "Troubleshooting & Debugging"
}
k8s_progress = create_subtask_section("Kubernetes", k8s_subtasks, "k8s")

# Helm / Kustomize
helm_subtasks = {
    "helm_basics": "Helm Basics (Charts, Releases, Repositories)",
    "helm_templates": "Helm Templates & Values",
    "helm_hooks": "Helm Hooks & Lifecycle",
    "kustomize_basics": "Kustomize Basics & Overlays",
    "kustomize_patches": "Kustomize Patches & Transformers",
    "package_management": "Package Management Strategies",
    "helm_security": "Helm Security & Best Practices"
}
helm_progress = create_subtask_section("Helm / Kustomize", helm_subtasks, "helm")

# Calculate overall Cloud progress
all_cloud_progress = [aws_progress, terraform_progress, k8s_progress, helm_progress]
cloud_total = sum([sum(section.values()) for section in all_cloud_progress])
cloud_count = sum([len(section) for section in all_cloud_progress])
cloud_progress = (cloud_total / cloud_count * 100) if cloud_count > 0 else 0

st.progress(cloud_progress / 100)
st.caption(f"Overall Cloud & IaC Progress: {cloud_progress:.0f}%")

st.divider()


# --- Section 4: Monitoring & Observability ---
st.markdown('<div id="monitoring"></div>', unsafe_allow_html=True)
st.subheader("📊 Monitoring & Observability")

# Prometheus / Grafana
prometheus_subtasks = {
    "prometheus_basics": "Prometheus Basics & Architecture",
    "metrics_collection": "Metrics Collection & Exporters",
    "promql": "PromQL Query Language",
    "alerting_rules": "Alerting Rules & Alertmanager",
    "grafana_dashboards": "Grafana Dashboards & Visualization",
    "grafana_alerts": "Grafana Alerting & Notifications",
    "service_discovery": "Service Discovery & Targets",
    "monitoring_best_practices": "Monitoring Best Practices"
}
prometheus_progress = create_subtask_section("Prometheus / Grafana", prometheus_subtasks, "prometheus")

# ELK / EFK Stack
elk_subtasks = {
    "elasticsearch": "Elasticsearch (Indexing, Searching, Clusters)",
    "logstash": "Logstash (Data Processing & Pipelines)",
    "kibana": "Kibana (Visualization & Dashboards)",
    "filebeat": "Filebeat & Log Shipping",
    "fluentd": "Fluentd & Log Collection",
    "log_parsing": "Log Parsing & Grok Patterns",
    "index_management": "Index Management & Lifecycle",
    "security_logging": "Security & Access Control"
}
elk_progress = create_subtask_section("ELK / EFK Stack", elk_subtasks, "elk")

# CloudWatch / Datadog
cloudwatch_subtasks = {
    "cloudwatch_metrics": "CloudWatch Metrics & Custom Metrics",
    "cloudwatch_logs": "CloudWatch Logs & Log Groups",
    "cloudwatch_alarms": "CloudWatch Alarms & SNS",
    "cloudwatch_dashboards": "CloudWatch Dashboards",
    "datadog_basics": "Datadog Basics & Agent Setup",
    "datadog_dashboards": "Datadog Dashboards & Widgets",
    "datadog_alerts": "Datadog Alerts & Monitors",
    "apm_tracing": "APM & Distributed Tracing"
}
cloudwatch_progress = create_subtask_section("CloudWatch / Datadog", cloudwatch_subtasks, "cloudwatch")

# Incident Management / On-call
incident_subtasks = {
    "incident_response": "Incident Response Procedures",
    "on_call_practices": "On-call Practices & Rotation",
    "escalation_procedures": "Escalation Procedures",
    "incident_tools": "Incident Management Tools (PagerDuty, Opsgenie)",
    "post_incident": "Post-Incident Reviews & RCA",
    "runbooks": "Runbooks & Documentation",
    "communication": "Incident Communication & Status Pages",
    "metrics_tracking": "Incident Metrics & KPIs"
}
incident_progress = create_subtask_section("Incident Management / On-call", incident_subtasks, "incident")

# Calculate overall Monitoring progress
all_monitoring_progress = [prometheus_progress, elk_progress, cloudwatch_progress, incident_progress]
monitoring_total = sum([sum(section.values()) for section in all_monitoring_progress])
monitoring_count = sum([len(section) for section in all_monitoring_progress])
mon_progress = (monitoring_total / monitoring_count * 100) if monitoring_count > 0 else 0

st.progress(mon_progress / 100)
st.caption(f"Overall Monitoring & Observability Progress: {mon_progress:.0f}%")

st.divider()

# --- Section 5: SRE Mindset & Advanced Practices ---
st.markdown('<div id="sre"></div>', unsafe_allow_html=True)
st.subheader("🧠 SRE Mindset & Advanced Practices")

# SLO / SLI / SLA
slo_subtasks = {
    "sli_definition": "SLI Definition & Measurement",
    "slo_setting": "SLO Setting & Target Definition",
    "sla_management": "SLA Management & Customer Agreements",
    "error_budget": "Error Budget Calculation & Tracking",
    "slo_monitoring": "SLO Monitoring & Alerting",
    "slo_reporting": "SLO Reporting & Dashboards"
}
slo_progress = create_subtask_section("SLO / SLI / SLA", slo_subtasks, "slo")

# Error Budgets & Toil Reduction
budget_subtasks = {
    "error_budget_concept": "Error Budget Concepts & Policy",
    "toil_identification": "Toil Identification & Measurement",
    "automation_prioritization": "Automation Prioritization",
    "capacity_planning": "Capacity Planning & Scaling",
    "reliability_engineering": "Reliability Engineering Practices",
    "toil_reduction": "Toil Reduction Strategies"
}
budget_progress = create_subtask_section("Error Budgets & Toil Reduction", budget_subtasks, "budget")

# Incident Response & RCA
rca_subtasks = {
    "incident_classification": "Incident Classification & Severity",
    "incident_response_process": "Incident Response Process & Timeline",
    "rca_methodology": "Root Cause Analysis Methodology",
    "blameless_postmortem": "Blameless Postmortems",
    "action_items": "Action Items & Follow-up",
    "incident_prevention": "Incident Prevention Strategies",
    "communication_protocols": "Communication Protocols",
    "learning_culture": "Learning Culture & Continuous Improvement"
}
rca_progress = create_subtask_section("Incident Response & RCA", rca_subtasks, "rca")

# Automation / CI Improvements
automation_subtasks = {
    "infrastructure_automation": "Infrastructure Automation",
    "deployment_automation": "Deployment Automation & Rollbacks",
    "testing_automation": "Testing Automation & Quality Gates",
    "monitoring_automation": "Monitoring & Alerting Automation",
    "self_healing": "Self-Healing Systems",
    "auto_scaling": "Auto-scaling & Resource Management",
    "pipeline_optimization": "CI/CD Pipeline Optimization",
    "automation_testing": "Automation Testing & Validation"
}
automation_progress = create_subtask_section("Automation / CI Improvements", automation_subtasks, "automation")

# Chaos Engineering
chaos_subtasks = {
    "chaos_principles": "Chaos Engineering Principles",
    "chaos_tools": "Chaos Tools (Chaos Monkey, Litmus, Gremlin)",
    "failure_injection": "Failure Injection & Scenarios",
    "blast_radius": "Blast Radius & Safety Measures",
    "chaos_experiments": "Chaos Experiments Design",
    "resilience_testing": "Resilience Testing & Validation",
    "gamedays": "Game Days & Disaster Recovery",
    "chaos_automation": "Chaos Automation & Scheduling"
}
chaos_progress = create_subtask_section("Chaos Engineering", chaos_subtasks, "chaos")

# Calculate overall SRE progress
all_sre_progress = [slo_progress, budget_progress, rca_progress, automation_progress, chaos_progress]
sre_total = sum([sum(section.values()) for section in all_sre_progress])
sre_count = sum([len(section) for section in all_sre_progress])
sre_progress = (sre_total / sre_count * 100) if sre_count > 0 else 0

st.progress(sre_progress / 100)
st.caption(f"Overall SRE Progress: {sre_progress:.0f}%")

st.divider()

# --- Section 6: Notes & Dashboard ---
st.markdown('<div id="notes"></div>', unsafe_allow_html=True)
st.subheader("📋 Dashboard & Personal Notes")

col1, col2, col3 = st.columns(3)
with col1:
    to_learn = st.text_area("📘 To Learn Next", 
                           value=st.session_state.notes['to_learn'],
                           placeholder="List upcoming tools or topics (e.g., ArgoCD, Loki, Ansible)...")
    st.session_state.notes['to_learn'] = to_learn
    
with col2:
    in_progress = st.text_area("🟡 In Progress", 
                              value=st.session_state.notes['in_progress'],
                              placeholder="What are you currently learning?")
    st.session_state.notes['in_progress'] = in_progress
    
with col3:
    completed = st.text_area("✅ Completed", 
                            value=st.session_state.notes['completed'],
                            placeholder="Note down what you've finished...")
    st.session_state.notes['completed'] = completed

# --- Save progress automatically ---
# Include notes in the progress data
st.session_state.progress['notes'] = st.session_state.notes
save_progress(st.session_state.progress)

# --- Footer ---
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("""
    **✅ Progress automatically saved!**  
    Your learning progress and notes are saved locally and will persist across sessions.
    """)
with col2:
    if not st.session_state.show_reset_confirmation:
        if st.button("🗑️ Reset Progress"):
            st.session_state.show_reset_confirmation = True
            st.rerun()
    else:
        # Show confirmation dialog
        st.warning("⚠️ **WARNING:** This will permanently delete all your progress and notes!")
        st.markdown("Are you sure you want to reset all progress?")
        
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ Yes, Reset", type="primary"):
                # Reset progress
                if os.path.exists(DATA_FILE):
                    os.remove(DATA_FILE)
                st.session_state.clear()
                st.success("✅ Progress has been reset!")
                st.rerun()
        with col_no:
            if st.button("❌ Cancel"):
                st.session_state.show_reset_confirmation = False
                st.rerun()

