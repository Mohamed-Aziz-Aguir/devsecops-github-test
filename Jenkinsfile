pipeline {
    agent any

    environment {
        APP_NAME = "secure-task-app"
        PYTHONPATH = "${env.WORKSPACE}"
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                echo "Building ${APP_NAME} - Build #${BUILD_NUMBER}"
            }
        }

        stage('Setup') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Lint') {
            parallel {
                stage('Flake8') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            flake8 app/ --max-line-length=100 --statistics || true
                        '''
                    }
                }
                stage('Pylint') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pylint app/ --fail-under=6.0 --exit-zero || true
                        '''
                    }
                }
            }
        }

        stage('Test') {
            steps {
                sh '''
                    . venv/bin/activate
                    pytest tests/ -v --cov=app --cov-report=term --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                }
            }
        }

        stage('Security') {
            parallel {
                stage('Bandit') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            bandit -r app/ -f json -o bandit-report.json || true
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'bandit-report.json', allowEmptyArchive: true
                        }
                    }
                }
                stage('Dependency Scan') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip-audit --requirement requirements.txt --format columns || true
                        '''
                    }
                }
            }
        }

        stage('Docker') {
            stages {
                stage('Build') {
                    steps {
                        script {
                            try {
                                sh '''
                                    # Pre-pull base image to avoid timeout
                                    docker pull python:3.11-slim || true
                                    docker build -t ${APP_NAME}:latest -f docker/Dockerfile .
                                    docker tag ${APP_NAME}:latest ${APP_NAME}:${BUILD_NUMBER}
                                '''
                            } catch (Exception e) {
                                echo "Docker build failed: ${e.getMessage()}"
                                echo "Attempting to build with cached base image..."
                                sh '''
                                    docker build --no-cache -t ${APP_NAME}:latest -f docker/Dockerfile .
                                '''
                            }
                        }
                    }
                }
                stage('Test') {
                    steps {
                        sh '''
                            # Cleanup
                            docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                            
                            # Run container
                            docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:latest
                            sleep 5
                            
                            # Test endpoints
                            curl -f http://localhost:5000/health > /dev/null
                            curl -f http://localhost:5000/ > /dev/null
                            curl -f http://localhost:5000/secure > /dev/null
                            
                            echo "Container tests passed!"
                        '''
                    }
                    post {
                        always {
                            sh '''
                                docker logs ${APP_NAME} || true
                                docker rm -f ${APP_NAME} || true
                            '''
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            sh '''
                docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                docker ps -q -f name=${APP_NAME}-test | grep -q . && docker rm -f ${APP_NAME}-test || true
            '''
            cleanWs()
        }
        success {
            echo "✅ Pipeline completed successfully! Build #${BUILD_NUMBER}"
        }
        failure {
            echo "❌ Pipeline failed! Check logs for details."
        }
    }
}
