pipeline {
    agent any

    environment {
        APP_NAME = "secure-task-app"
    }

    options {
        timestamps()
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
                '''
            }
        }

        stage('Flake8') {
            steps {
                sh '''
                    . venv/bin/activate
                    flake8 app --max-line-length=100 || true
                '''
            }
        }

        stage('Pylint') {
            steps {
                sh '''
                    . venv/bin/activate
                    pylint app || true
                '''
            }
        }

        stage('Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    pytest -q || true
                '''
            }
        }

        stage('Bandit') {
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
                    docker build -t ${APP_NAME} -f docker/Dockerfile .
                '''
            }
        }

        stage('Run Container') {
            steps {
                sh '''
                    docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}
                '''
            }
        }
    }

    post {
        always {
            sh '''
                docker ps -q -f name=secure-task-app | grep -q . && docker rm -f secure-task-app || true
            '''
            cleanWs()
        }
    }
}
