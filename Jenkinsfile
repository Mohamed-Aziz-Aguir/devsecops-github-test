pipeline {
    agent any

    environment {
        APP_NAME         = "secure-task-app"
        APP_VERSION      = "1.0.${BUILD_NUMBER}"
        DOCKER_REGISTRY  = "docker.io"
        DOCKER_NAMESPACE = "mohamedazizaguir"
        DOCKER_IMAGE     = "${DOCKER_REGISTRY}/${DOCKER_NAMESPACE}/${APP_NAME}"
        PYTHONPATH       = "${env.WORKSPACE}"

        SONAR_HOST_URL   = "http://localhost:9000"
        SONAR_TOKEN      = credentials('sonar-token')
        DOCKER_CREDS     = credentials('Docker-Hub')

        // Add sonar-scanner to PATH so Jenkins can find it
        PATH             = "/opt/sonar-scanner/bin:${env.PATH}"
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
                    pytest tests/ -v \
                        --cov=app \
                        --cov-report=xml:coverage.xml \
                        --cov-report=html \
                        --cov-report=term \
                        --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                    publishHTML([
                        reportDir: 'htmlcov',
                        reportFiles: 'index.html',
                        reportName: 'Coverage Report',
                        allowMissing: true,
                        keepAll: true,
                        alwaysLinkToLastBuild: false
                    ])
                }
            }
        }

        // ✅ Security Scanning is now a proper top-level stage (was wrongly nested before)
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
                                reportName: 'Bandit Security Report',
                                allowMissing: true,
                                keepAll: true,
                                alwaysLinkToLastBuild: false
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
                sh '''
                    echo "Running SonarQube analysis..."
                    sonar-scanner \
                        -Dsonar.projectKey=${APP_NAME} \
                        -Dsonar.projectName="${APP_NAME}" \
                        -Dsonar.projectVersion=${APP_VERSION} \
                        -Dsonar.sources=app \
                        -Dsonar.tests=tests \
                        -Dsonar.python.coverage.reportPaths=coverage.xml \
                        -Dsonar.exclusions=**/venv/**,**/__pycache__/** \
                        -Dsonar.coverage.exclusions=**/tests/**,**/__pycache__/** \
                        -Dsonar.sourceEncoding=UTF-8 \
                        -Dsonar.host.url=${SONAR_HOST_URL} \
                        -Dsonar.token=${SONAR_TOKEN}
                    echo "SonarQube analysis completed!"
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    echo "Building Docker image..."
                    docker build -t ${APP_NAME}:${APP_VERSION} -f docker/Dockerfile .
                    docker tag ${APP_NAME}:${APP_VERSION} ${APP_NAME}:latest
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${APP_VERSION}
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:latest
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                    echo "Docker images built:"
                    docker images | grep ${APP_NAME}
                '''
            }
        }

        stage('Trivy Security Scan') {
            steps {
                sh '''
                    echo "Scanning Docker image with Trivy..."
                    mkdir -p trivy-reports
                    if command -v trivy > /dev/null 2>&1; then
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
                    fi
                '''
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
                    curl -f http://localhost:5000/health
                    curl -f http://localhost:5000/
                    curl -f http://localhost:5000/secure
                    curl -f http://localhost:5000/metrics
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
            // ✅ Removed broken env.DOCKER_CREDS check — guard on branch only
            when {
                anyOf {
                    branch 'main'
                    branch 'master'
                }
            }
            steps {
                sh '''
                    echo "Logging into Docker Hub..."
                    echo "${DOCKER_CREDS_PSW}" | docker login -u "${DOCKER_CREDS_USR}" --password-stdin
                    docker push ${DOCKER_IMAGE}:${APP_VERSION}
                    docker push ${DOCKER_IMAGE}:latest
                    docker push ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                    echo "Images pushed successfully!"
                    docker logout
                '''
            }
        }

    } // end stages

    post {
        always {
            sh '''
                docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                docker images ${APP_NAME} --format "{{.Repository}}:{{.Tag}}" | tail -n +6 | xargs -r docker rmi || true
            '''
            cleanWs()
        }
        success {
            echo "========================================="
            echo "PIPELINE COMPLETED SUCCESSFULLY!"
            echo "Build: ${APP_NAME}:${APP_VERSION}"
            echo "Git Commit: ${env.GIT_COMMIT_SHORT}"
            echo "SonarQube: ${SONAR_HOST_URL}/dashboard?id=${APP_NAME}"
            echo "========================================="
        }
        failure {
            echo "========================================="
            echo "PIPELINE FAILED - Check logs above"
            echo "Build: ${APP_NAME} #${BUILD_NUMBER}"
            echo "========================================="
        }
    }
}
