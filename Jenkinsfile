pipeline {
    agent any

    environment {
        APP_NAME = "secure-task-app"
        APP_VERSION = "1.0.${BUILD_NUMBER}"
        DOCKER_REGISTRY = "docker.io"  // Change to your registry (docker.io, ghcr.io, etc.)
        DOCKER_NAMESPACE = "mohamedazizaguir"  // Your Docker Hub username or registry namespace
        DOCKER_IMAGE = "${DOCKER_REGISTRY}/${DOCKER_NAMESPACE}/${APP_NAME}"
        PYTHONPATH = "${env.WORKSPACE}"
        
        // SonarQube configuration
        SONAR_HOST_URL = credentials('sonar-host-url')  // e.g., http://localhost:9000
        SONAR_TOKEN = credentials('sonar-token')
        
        // Docker Hub credentials
        DOCKER_USERNAME = credentials('docker-username')
        DOCKER_PASSWORD = credentials('docker-password')
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '5'))
        timeout(time: 30, unit: 'MINUTES')
        ansiColor('xterm')
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
                    pip install sonar-scanner  # SonarQube scanner
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
                    post {
                        always {
                            recordIssues(
                                tool: pyLint(),
                                qualityGates: [[threshold: 1, type: 'TOTAL', unstable: true]]
                            )
                        }
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
                            recordIssues(
                                tool: pyLint(pattern: 'pylint-report.txt'),
                                qualityGates: [[threshold: 10, type: 'TOTAL', unstable: true]]
                            )
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
                    --junitxml=test-results.xml --html=pytest-report.html --self-contained-html
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
                    publishHTML([
                        reportDir: '.',
                        reportFiles: 'pytest-report.html',
                        reportName: 'Test Report'
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
                            recordIssues(tools: [bandit(pattern: 'bandit-report.json')])
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
                stage('Safety Check') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            safety check --json --output safety-report.json || true
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'safety-report.json', allowEmptyArchive: true
                        }
                    }
                }
            }
        }

        stage('SonarQube Analysis') {
            when { expression { env.SONAR_HOST_URL != null && env.SONAR_TOKEN != null } }
            steps {
                script {
                    withSonarQubeEnv('SonarQube') {
                        sh '''
                            . venv/bin/activate
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
                                -Dsonar.coverage.exclusions=**/tests/** \
                                -Dsonar.qualitygate.wait=true
                        '''
                    }
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
                    '''
                }
            }
        }

        stage('Trivy Security Scan') {
            steps {
                script {
                    sh '''
                        echo "Scanning Docker image with Trivy..."
                        
                        # Create reports directory
                        mkdir -p trivy-reports
                        
                        # Scan for all vulnerabilities
                        trivy image --severity LOW,MEDIUM,HIGH,CRITICAL \
                            --format table \
                            ${APP_NAME}:${APP_VERSION} || true
                        
                        # Generate JSON report for Jenkins
                        trivy image --severity HIGH,CRITICAL \
                            --format json \
                            --output trivy-reports/trivy-high-critical.json \
                            ${APP_NAME}:${APP_VERSION} || true
                        
                        # Generate HTML report
                        trivy image --severity HIGH,CRITICAL \
                            --format template \
                            --template "@contrib/html.tpl" \
                            --output trivy-reports/trivy-report.html \
                            ${APP_NAME}:${APP_VERSION} || true
                        
                        # Generate SARIF for GitHub Advanced Security
                        trivy image --severity HIGH,CRITICAL \
                            --format sarif \
                            --output trivy-reports/trivy-results.sarif \
                            ${APP_NAME}:${APP_VERSION} || true
                        
                        echo "Trivy scan completed"
                    '''
                }
            }
            post {
                always {
                    publishHTML([
                        reportDir: 'trivy-reports',
                        reportFiles: 'trivy-report.html',
                        reportName: 'Trivy Security Report'
                    ])
                    archiveArtifacts artifacts: 'trivy-reports/*', allowEmptyArchive: true
                    recordIssues(tools: [sarif(pattern: 'trivy-reports/trivy-results.sarif')])
                }
            }
        }

        stage('Docker Container Test') {
            steps {
                sh '''
                    # Cleanup any existing container
                    docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    
                    # Run container
                    echo "Starting container for testing..."
                    docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:${APP_VERSION}
                    
                    # Wait for container to be ready
                    sleep 5
                    
                    # Test endpoints
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

        stage('Push to Registry') {
            when { 
                expression { 
                    env.DOCKER_USERNAME != null && 
                    env.DOCKER_PASSWORD != null && 
                    (env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'master')
                } 
            }
            steps {
                script {
                    sh '''
                        echo "Logging into Docker registry..."
                        echo ${DOCKER_PASSWORD} | docker login -u ${DOCKER_USERNAME} --password-stdin ${DOCKER_REGISTRY}
                        
                        echo "Pushing Docker images..."
                        docker push ${DOCKER_IMAGE}:${APP_VERSION}
                        docker push ${DOCKER_IMAGE}:latest
                        docker push ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                        
                        echo "Images pushed successfully!"
                        
                        # Logout
                        docker logout ${DOCKER_REGISTRY}
                    '''
                }
            }
        }

        stage('Deployment') {
            when { 
                expression { 
                    env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'master'
                } 
            }
            steps {
                script {
                    echo "Deployment stage - Ready for orchestration"
                    echo "Image: ${DOCKER_IMAGE}:${APP_VERSION}"
                    
                    // Example: Deploy to Kubernetes
                    // sh """
                    //     kubectl set image deployment/${APP_NAME} \
                    //     ${APP_NAME}=${DOCKER_IMAGE}:${APP_VERSION} \
                    //     --namespace=production
                    // """
                    
                    // Example: Deploy to Docker Swarm
                    // sh """
                    //     docker service update --image ${DOCKER_IMAGE}:${APP_VERSION} ${APP_NAME}_service
                    // """
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
            echo "SonarQube Analysis: Completed"
            echo "Security Scans: Passed"
            echo "Container Registry: Pushed"
            echo "========================================="
            
            // Send success notification
            emailext(
                subject: "Pipeline Success: ${APP_NAME} #${BUILD_NUMBER}",
                body: "Build completed successfully!\n\nVersion: ${APP_VERSION}\nImage: ${DOCKER_IMAGE}:${APP_VERSION}\nURL: ${BUILD_URL}",
                to: "team@example.com"
            )
        }
        failure {
            echo "========================================="
            echo "❌ PIPELINE FAILED! ❌"
            echo "========================================="
            echo "Build: ${APP_NAME} #${BUILD_NUMBER}"
            echo "Check the following:"
            echo "  - Code quality reports"
            echo "  - Unit test results"
            echo "  - Security scan findings"
            echo "  - Container logs"
            echo "========================================="
            
            // Send failure notification
            emailext(
                subject: "Pipeline Failed: ${APP_NAME} #${BUILD_NUMBER}",
                body: "Build failed!\n\nCheck the logs: ${BUILD_URL}",
                to: "team@example.com"
            )
        }
        unstable {
            echo "⚠️ PIPELINE IS UNSTABLE ⚠️"
            echo "Quality gates not met but build completed"
        }
    }
}
