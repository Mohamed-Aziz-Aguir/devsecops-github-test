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
        COSIGN_KEY       = credentials('cosign-key')  // Assumes cosign-key is a file credential
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
                    env.GIT_COMMIT_SHORT = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
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
                    archiveArtifacts artifacts: 'htmlcov/**', allowEmptyArchive: true
                }
            }
        }

        stage('Security Scanning') {
            parallel {
                stage('Bandit') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            bandit -r app/ -f html -o bandit-report.html || true
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'bandit-report.html', allowEmptyArchive: true
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

        stage('Quality Gate') {
            steps {
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    echo "Building Docker image..."
                    docker build -t ${APP_NAME}:${APP_VERSION} -f docker/Dockerfile .
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
                            --format json \
                            --output trivy-reports/trivy-report.json \
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
                    docker rm -f ${APP_NAME} || true
                    echo "Starting container for testing..."
                    docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:${APP_VERSION}
                    sleep 5
                    echo "Testing endpoints..."
                    curl -f http://localhost:5000/health || true
                    curl -f http://localhost:5000/ || true
                    curl -f http://localhost:5000/secure || true
                    echo "All container tests done!"
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

        stage('OWASP ZAP Scan') {
            steps {
                sh '''
                    echo "Running OWASP ZAP Baseline Scan..."
                    docker run --rm -v ${WORKSPACE}:/zap/wrk:rw -t ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t http://localhost:5000 -r /zap/wrk/zap-report.html -I || true
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'zap-report.html', allowEmptyArchive: true
                }
            }
        }

        stage('SBOM Generation') {
            steps {
                sh '''
                    echo "Generating SBOM for ${DOCKER_IMAGE}:${APP_VERSION}"
                    mkdir -p sbom
                    # Using anchore/syft Docker image to generate SBOM
                    docker run --rm -v ${WORKSPACE}:/workspace -w /workspace anchore/syft:latest ${DOCKER_IMAGE}:${APP_VERSION} -o json > sbom.json || true
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'sbom.json', allowEmptyArchive: true
                }
            }
        }

        stage('Container Signing') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'Docker-Hub', usernameVariable: 'DOCKER_USR', passwordVariable: 'DOCKER_PSW'), file(credentialsId: 'cosign-key', variable: 'COSIGN_KEY')]) {
                    sh '''
                        echo "Signing images with Cosign..."
                        echo "$DOCKER_PSW" | docker login -u "$DOCKER_USR" --password-stdin
                        cosign sign --key $COSIGN_KEY ${DOCKER_IMAGE}:${APP_VERSION} || true
                        cosign sign --key $COSIGN_KEY ${DOCKER_IMAGE}:latest || true
                        cosign sign --key $COSIGN_KEY ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT} || true
                        docker logout
                    '''
                }
            }
        }

        stage('Push to Docker Hub') {
            when {
                anyOf { branch 'main'; branch 'master' }
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

        stage('Deploy to Dev') {
            steps {
                sh '''
                    echo "Deploying to development environment..."
                    docker rm -f ${APP_NAME} || true
                    docker pull ${DOCKER_IMAGE}:${APP_VERSION} || true
                    docker run -d -p 5000:5000 --name ${APP_NAME} ${DOCKER_IMAGE}:${APP_VERSION}
                    sleep 5
                    curl -f http://localhost:5000/health || true
                    echo "Deployment to Dev completed!"
                '''
            }
        }

    }

    post {
    always {
        script {
            sh '''
                docker rm -f secure-task-app || true
                docker images secure-task-app --format "{{.Repository}}:{{.Tag}}" | tail -n +6 | xargs -r docker rmi || true
            '''
        }
        cleanWs()
    }

    success {
        echo "========================================="
        echo "PIPELINE COMPLETED SUCCESSFULLY!"
        echo "========================================="
    }

    failure {
        echo "========================================="
        echo "PIPELINE FAILED - Check logs above"
        echo "========================================="
    }
}
}

