import firebase_admin
from firebase_admin import credentials, firestore
import subprocess
import difflib
import asyncio
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify
from flask_cors import CORS  # Import CORS


# Initialize Firestore
cred = credentials.Certificate(r"D:\py\My Chatbot\from google\ai-data-d7b25-firebase-adminsdk-4d6my-3ff0c403c4.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)
CORS(app)
# Function to query OLLAMA with timeout and proper encoding handling
def query_ollama(prompt, timeout=180):
    try:
        result = subprocess.run(
            ['ollama', 'run', 'llama3', prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            stdin=subprocess.DEVNULL
        )
        if result.returncode != 0:
            print(f"Command failed with error: {result.stderr.strip()}")
            return {"response": f"Command failed with error: {result.stderr.strip()}"}
        return {"response": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        print(f"Command '{prompt}' timed out after {timeout} seconds.")
        return {"response": "Command timed out."}

# Function to retrieve skills and tools from Firestore
def get_skills_and_tools():
    doc_ids = ['Skills', 'Tools']
    skills_and_tools = {}

    for doc_id in doc_ids:
        doc_ref = db.collection('SKILLS').document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            if data:  # Check if document has data
                skills_and_tools[doc_id] = data
            else:
                print(f"{doc_id} document exists but is empty.")
        else:
            print(f"No data found for {doc_id}.")
    
    return skills_and_tools

# Function to generate an introduction based on skills and tools
def generate_skills_introduction(skills_and_tools):
    skills = skills_and_tools.get('Skills', {})
    tools = skills_and_tools.get('Tools', {})

    prompt = "Generate a brief introduction about a person with the following skills and tools experience:\n"
    prompt += "Skills:\n"
    for skill, level in skills.items():
        prompt += f"- {skill}: {level}\n"
    prompt += "Tools:\n"
    for tool, proficiency in tools.items():
        prompt += f"- {tool}: {proficiency}\n"
    
    prompt += "\nIntroduction:"

    return query_ollama(prompt)

# Function to retrieve project details along with their GitHub links
async def get_projects_with_links():
    try:
        project_ref = db.collection('Projects').document('Projects Done').get()
        github_ref = db.collection('Projects').document('GitHub links').get()

        project_data = project_ref.to_dict() if project_ref.exists else {}
        github_data = github_ref.to_dict() if github_ref.exists else {}

        if not project_data:
            print("Projects Done document does not exist.")
            return []
        if not github_data:
            print("GitHub links document does not exist.")
            return []

        projects_info = []
        for project_name, project_desc in project_data.items():
            closest_match = difflib.get_close_matches(project_name, github_data.keys(), n=1, cutoff=0.6)
            github_link = github_data.get(closest_match[0], "No link found") if closest_match else "No link found"
            projects_info.append({
                'name': project_name,
                'desc': project_desc,
                'github_link': github_link
            })
        return projects_info
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

# Function to process OLLAMA descriptions in parallel with timeout
async def generate_ollama_descriptions(projects):
    def ollama_task(project):
        prompt = f"summarize the project in few sentences for a project called '{project['name']}'. Here is the brief description: {project['desc']}."
        return project['name'], query_ollama(prompt), project['github_link']

    with ThreadPoolExecutor() as executor:
        project_results = await asyncio.gather(*[asyncio.to_thread(ollama_task, project) for project in projects])

    return list(project_results)

# Function to format project details
def format_projects(projects):
    if projects:
        formatted_projects = []
        for name, ollama_desc, github_link in projects:
            ollama_desc = ollama_desc['response'] if ollama_desc else "Description not available."
            formatted_projects.append(f"**{name}**:\n{ollama_desc}\nGitHub Link: {github_link}")
        return f"Here are Fatheen Khan's projects:\n" + "\n\n".join(formatted_projects)
    else:
        return "No projects found."

# Function to retrieve certifications from multiple document IDs
def get_certifications():
    doc_ids = ['AI ML', 'CLOUD']
    certifications = []
    for doc_id in doc_ids:
        doc_ref = db.collection('Certifications').document(doc_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            for key, value in data.items():
                certifications.append(f"{key}: {value}")
    return certifications

# Function to retrieve education details and format them into a structured response
def get_education():
    document_ids = ['Schooling', 'Under Graduate']
    schooling_info = []
    undergraduate_info = []

    for doc_id in document_ids:
        doc_ref = db.collection('Education').document(doc_id)
        edu_data = doc_ref.get().to_dict()
        if edu_data:
            for field_name, field_value in edu_data.items():
                if doc_id == 'Schooling':
                    schooling_info.append(f"{field_name}: {field_value}")
                elif doc_id == 'Under Graduate':
                    undergraduate_info.append(f"{field_name}: {field_value}")

    schooling_text = " and ".join(schooling_info) if schooling_info else "no schooling information."
    undergraduate_text = " and ".join(undergraduate_info) if undergraduate_info else "no undergraduate information."

    return (f"Fatheen has completed his schooling at {schooling_text}. "
            f"In his undergraduate studies, he completed {undergraduate_text}.")

# Route to handle chatbot queries
@app.route('/chat', methods=['POST'])
async def chat():
    data = request.json
    prompt = data.get('prompt', '').strip()

    if not prompt:
        return jsonify({"response": "Prompt is required"}), 400

    if "certification" in prompt.lower():
        certifications = get_certifications()
        return jsonify({"response": certifications})

    elif "education" in prompt.lower():
        education = get_education()
        return jsonify({"response": education})

    elif "projects" in prompt.lower():
        projects = await get_projects_with_links()
        if projects:
            descriptions = await generate_ollama_descriptions(projects)
            response = format_projects(descriptions)
            return jsonify({"response": response})
        else:
            return jsonify({"response": "No projects found."})

    elif "skills" in prompt.lower() or "tools" in prompt.lower():
        skills_and_tools = get_skills_and_tools()
        if skills_and_tools:
            introduction = generate_skills_introduction(skills_and_tools)
            return jsonify(introduction)
        else:
            return jsonify({"response": "No skills or tools information found."})
    
    else:
        output = query_ollama(prompt)
        return jsonify({"response": output['response']})

if __name__ == "__main__":
    app.run(host="0.0.0.0",debug=True)

