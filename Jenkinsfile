pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 1, unit: 'HOURS')
        disableConcurrentBuilds()
    }

    environment {
        VENV = "venv"
        APP_NAME = "secure-task-app"
    }

    stages {

        stage('📥 Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('🐍 Setup Python Environment') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip setuptools wheel
                    pip install -r requirements.txt
                    pip install flake8 pylint bandit pip-audit pytest pytest-cov
                '''
            }
        }

        stage('🎨 Flake8') {
            steps {
                sh '''
                    . venv/bin/activate
                    flake8 app/ --max-line-length=100
                '''
            }
        }

        stage('🧠 Pylint') {
            steps {
                sh '''
                    . venv/bin/activate
                    pylint app --disable=all --enable=E,W --exit-zero
                '''
            }
        }

        stage('🧪 Unit Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    pytest -q --disable-warnings --maxfail=1 || true
                '''
            }
        }

        stage('🔐 Bandit SAST') {
            steps {
                sh '''
                    . venv/bin/activate
                    bandit -r app -f txt || true
                '''
            }
        }

        stage('📦 Dependency Scan') {
            steps {
                sh '''
                    . venv/bin/activate
                    pip-audit || true
                '''
            }
        }

        stage('🐳 Docker Build') {
            steps {
                sh '''
                    docker build -t secure-task-app docker/
                '''
            }
        }

        stage('🔎 Trivy Image Scan') {
            steps {
                sh '''
                    trivy image secure-task-app || true
                '''
            }
        }

        stage('🚀 Run Container') {
            steps {
                sh '''
                    docker rm -f secure-task-app || true
                    docker run -d -p 5000:5000 --name secure-task-app secure-task-app
                '''
            }
        }

        stage('🕷️ OWASP ZAP') {
            steps {
                sh '''
                    echo "DAST skipped in local run (needs target URL)"
                '''
            }
        }
    }

    post {
        always {
            sh 'docker rm -f secure-task-app || true'
            cleanWs()
        }
    }
}
