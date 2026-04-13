pipeline {
    agent any

    environment {
        VENV = "venv"
        IMAGE_NAME = "secure-task-app"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup Python') {
            steps {
                sh '''
                python3 -m venv venv
                . venv/bin/activate
                pip install --upgrade pip
                pip install -r requirements.txt
                '''
            }
        }

        stage('Lint - Flake8') {
            steps {
                sh '''
                . venv/bin/activate
                flake8 app --max-line-length=100 || true
                '''
            }
        }

        stage('Lint - Pylint') {
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
                docker build -t $IMAGE_NAME -f docker/Dockerfile .
                '''
            }
        }

        stage('Run Container') {
            steps {
                sh '''
                docker rm -f $IMAGE_NAME || true
                docker run -d -p 5000:5000 --name $IMAGE_NAME $IMAGE_NAME
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
