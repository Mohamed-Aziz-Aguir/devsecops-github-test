pipeline {
    agent any

    environment {
        SONAR_TOKEN = credentials('sonar-token')
        PATH = "/opt/sonar-scanner/bin:/usr/local/bin:/usr/bin:/bin"
    }

    stages {

        stage('Checkout') {
            steps {
                git 'https://github.com/Mohamed-Aziz-Aguir/devsecops-github-test.git'
            }
        }

        stage('Python Quality') {
            steps {
                sh '''
                pip install flake8 pylint
                flake8 .
                pylint *.py || true
                '''
            }
        }

        stage('Bandit Security') {
            steps {
                sh '''
                pip install bandit
                bandit -r . || true
                '''
            }
        }

        stage('Dependency Scan') {
            steps {
                sh '''
                pip install pip-audit
                pip-audit || true
                '''
            }
        }

        stage('SonarQube') {
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh '''
                    sonar-scanner \
                    -Dsonar.projectKey=devsecops-test \
                    -Dsonar.sources=. \
                    -Dsonar.host.url=http://localhost:9000 \
                    -Dsonar.login=$SONAR_TOKEN
                    '''
                }
            }
        }

        stage('Trivy FS Scan') {
            steps {
                sh 'trivy fs .'
            }
        }

        stage('Docker Build') {
            steps {
                sh 'docker build -t flask-app:latest .'
            }
        }

        stage('Trivy Image Scan') {
            steps {
                sh 'trivy image flask-app:latest'
            }
        }

        stage('Run App') {
            steps {
                sh 'docker run -d -p 5000:5000 flask-app:latest || true'
            }
        }

        stage('ZAP Scan') {
            steps {
                sh 'zap-baseline.py -t http://localhost:5000 || true'
            }
        }
    }
}
