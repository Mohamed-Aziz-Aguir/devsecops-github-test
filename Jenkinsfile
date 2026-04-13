pipeline {
    agent any

    environment {
        APP_NAME = "secure-task-app"
        VENV = "venv"
    }

    options {
        timestamps()
        timeout(time: 1, unit: 'HOURS')
        disableConcurrentBuilds()
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup Environment') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                    pip install flake8 pylint bandit pytest pip-audit
                '''
            }
        }

        stage('Lint - Flake8') {
            steps {
                sh '''
                    . venv/bin/activate
                    flake8 app --max-line-length=100
                '''
            }
        }

        stage('Lint - Pylint') {
            steps {
                sh '''
                    . venv/bin/activate
                    pylint app --exit-zero
                '''
            }
        }

        stage('Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    pytest tests || true
                '''
            }
        }

        stage('SAST - Bandit') {
            steps {
                sh '''
                    . venv/bin/activate
                    bandit -r app || true
                '''
            }
        }

        stage('Dependency Scan') {
            steps {
                sh '''
                    . venv/bin/activate
                    pip-audit || true
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    docker build -t secure-task-app .
                '''
            }
        }

        stage('Run Container') {
            steps {
                sh '''
                    docker rm -f secure-task-app || true
                    docker run -d -p 5000:5000 --name secure-task-app secure-task-app
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
