pipeline {
    agent any

    environment {
        APP_NAME = "secure-task-app"
        APP_VERSION = "1.0.${BUILD_NUMBER}"
        DOCKER_REGISTRY = "docker.io"
        DOCKER_NAMESPACE = "mohamedazizaguir"
        DOCKER_IMAGE = "${DOCKER_REGISTRY}/${DOCKER_NAMESPACE}/${APP_NAME}"
        PYTHONPATH = "${env.WORKSPACE}"
        
        // SonarQube configuration
        SONAR_HOST_URL = "http://localhost:9000"  // Update with your SonarQube URL
        SONAR_TOKEN = credentials('sonar-token')
        
        // Docker credentials
        DOCKER_CREDS = credentials('Docker-Hub')
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '5'))
        timeout(time: 30, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                echo "Building ${APP_NAME} - Version: ${APP_VERSION} - Build #${BUILD_NUMBER}"
                script {
                    def gitCommit = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
                    env.GIT_COMMIT_SHORT = gitCommit
                    echo "Git Commit: ${env.GIT_COMMIT_SHORT}"
                }
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
                            flake8 app/ --max-line-length=100 --statistics --count || true
                        '''
                    }
                }
                stage('Pylint') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pylint app/ --fail-under=6.0 --exit-zero --output-format=parseable > pylint-report.txt || true
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'pylint-report.txt', allowEmptyArchive: true
                        }
                    }
                }
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    pytest tests/ -v --cov=app --cov-report=xml --cov-report=html --cov-report=term \
                    --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                    publishHTML([
                        reportDir: 'htmlcov',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report'
                    ])
                }
            }
        }

        stage('Security Scanning') {
            parallel {
                stage('Bandit') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            bandit -r app/ -f json -o bandit-report.json || true
                            bandit -r app/ -f html -o bandit-report.html || true
                        '''
                    }
                    post {
                        always {
                            publishHTML([
                                reportDir: '.',
                                reportFiles: 'bandit-report.html',
                                reportName: 'Bandit Security Report'
                            ])
                            archiveArtifacts artifacts: 'bandit-report.json', allowEmptyArchive: true
                        }
                    }
                }
                stage('Dependency Scan') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip-audit --requirement requirements.txt --format json --output audit-report.json || true
                            pip-audit --requirement requirements.txt --format columns || true
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'audit-report.json', allowEmptyArchive: true
                        }
                    }
                }
            }
        }

        stage('SonarQube Analysis') {
            when { expression { env.SONAR_TOKEN != null && env.SONAR_TOKEN != '' } }
            steps {
                script {
                    // Using existing sonar-scanner installation
                    sh '''
                        echo "Running SonarQube analysis..."
                        sonar-scanner \
                            -Dsonar.projectKey=${APP_NAME} \
                            -Dsonar.projectName="${APP_NAME}" \
                            -Dsonar.projectVersion=${APP_VERSION} \
                            -Dsonar.sources=app \
                            -Dsonar.tests=tests \
                            -Dsonar.python.coverage.reportPaths=coverage.xml \
                            -Dsonar.python.pylint.reportPath=pylint-report.txt \
                            -Dsonar.python.bandit.reportPath=bandit-report.json \
                            -Dsonar.exclusions=**/venv/**,**/tests/** \
                            -Dsonar.coverage.exclusions=**/tests/**,**/__pycache__/** \
                            -Dsonar.host.url=${SONAR_HOST_URL} \
                            -Dsonar.login=${SONAR_TOKEN}
                        
                        echo "SonarQube analysis completed!"
                    '''
                }
            }
        }

        stage('Docker Build') {
            steps {
                script {
                    sh '''
                        echo "Building Docker image..."
                        docker build -t ${APP_NAME}:${APP_VERSION} -f docker/Dockerfile .
                        docker tag ${APP_NAME}:${APP_VERSION} ${APP_NAME}:latest
                        docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${APP_VERSION}
                        docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:latest
                        docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                        
                        echo "Docker images built successfully:"
                        docker images | grep ${APP_NAME}
                    '''
                }
            }
        }

        stage('Trivy Security Scan') {
            steps {
                script {
                    sh '''
                        echo "Scanning Docker image with Trivy..."
                        
                        mkdir -p trivy-reports
                        
                        if command -v trivy &> /dev/null; then
                            trivy image --severity HIGH,CRITICAL \
                                --format table \
                                ${APP_NAME}:${APP_VERSION} || true
                            
                            trivy image --severity HIGH,CRITICAL \
                                --format json \
                                --output trivy-reports/trivy-high-critical.json \
                                ${APP_NAME}:${APP_VERSION} || true
                            
                            echo "Trivy scan completed"
                        else
                            echo "Trivy not installed - skipping scan"
                            echo "Install with: sudo apt-get install trivy"
                        fi
                    '''
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-reports/*', allowEmptyArchive: true
                }
            }
        }

        stage('Docker Container Test') {
            steps {
                sh '''
                    docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    
                    echo "Starting container for testing..."
                    docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:${APP_VERSION}
                    sleep 5
                    
                    echo "Testing endpoints..."
                    curl -f http://localhost:5000/health > /dev/null
                    curl -f http://localhost:5000/ > /dev/null
                    curl -f http://localhost:5000/secure > /dev/null
                    curl -f http://localhost:5000/metrics > /dev/null
                    
                    echo "All container tests passed!"
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

        stage('Push to Docker Hub') {
            when { 
                expression { 
                    env.DOCKER_CREDS != null && 
                    (env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'master')
                } 
            }
            steps {
                script {
                    sh '''
                        echo "Logging into Docker Hub..."
                        echo "${DOCKER_CREDS_PSW}" | docker login -u "${DOCKER_CREDS_USR}" --password-stdin
                        
                        echo "Pushing Docker images to registry..."
                        docker push ${DOCKER_IMAGE}:${APP_VERSION}
                        docker push ${DOCKER_IMAGE}:latest
                        docker push ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                        
                        echo "✅ Images pushed successfully!"
                        echo "Image available at: ${DOCKER_IMAGE}:${APP_VERSION}"
                        
                        docker logout
                    '''
                }
            }
        }
    }

    post {
        always {
            script {
                sh '''
                    echo "Cleaning up resources..."
                    docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    docker ps -q -f name=${APP_NAME}-test | grep -q . && docker rm -f ${APP_NAME}-test || true
                    
                    # Keep only last 5 images
                    docker images ${APP_NAME} --format "{{.Repository}}:{{.Tag}}" | tail -n +2 | head -n -5 | xargs -r docker rmi || true
                '''
            }
            cleanWs()
        }
        success {
            echo "========================================="
            echo "✅ PIPELINE COMPLETED SUCCESSFULLY! ✅"
            echo "========================================="
            echo "Build: ${APP_NAME}:${APP_VERSION}"
            echo "Git Commit: ${env.GIT_COMMIT_SHORT}"
            echo "Docker Image: ${DOCKER_IMAGE}:${APP_VERSION}"
            echo "SonarQube Dashboard: ${SONAR_HOST_URL}/dashboard?id=${APP_NAME}"
            echo "========================================="
        }
        failure {
            echo "========================================="
            echo "❌ PIPELINE FAILED! ❌"
            echo "========================================="
            echo "Build: ${APP_NAME} #${BUILD_NUMBER}"
            echo "Check the logs above for details."
            echo "========================================="
        }
    }
}
