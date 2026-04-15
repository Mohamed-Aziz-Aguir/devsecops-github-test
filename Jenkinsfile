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

        PATH = "/opt/sonar-scanner/bin:${env.PATH}"
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm

                script {
                    env.GIT_COMMIT_SHORT = sh(
                        script: "git rev-parse --short HEAD",
                        returnStdout: true
                    ).trim()

                    echo "Commit: ${env.GIT_COMMIT_SHORT}"
                }
            }
        }

        stage('Setup Python') {
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
                        flake8 app/ --max-line-length=100 || true
                        '''
                    }
                }

                stage('Pylint') {
                    steps {
                        sh '''
                        . venv/bin/activate
                        pylint app/ --exit-zero > pylint-report.txt || true
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
                  --cov-report=xml \
                  --cov-report=html \
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
                        alwaysLinkToLastBuild: true
                    ])
                }
            }
        }

        stage('Security Scan') {

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
                            publishHTML([
                                reportDir: '.',
                                reportFiles: 'bandit-report.html',
                                reportName: 'Bandit Security Report',
                                allowMissing: true,
                                keepAll: true,
                                alwaysLinkToLastBuild: true
                            ])
                        }
                    }
                }

                stage('Dependency Scan') {
                    steps {
                        sh '''
                        . venv/bin/activate
                        pip-audit -r requirements.txt || true
                        '''
                    }
                }
            }
        }

        stage('SonarQube Analysis') {
            steps {
                sh '''
                sonar-scanner \
                  -Dsonar.projectKey=${APP_NAME} \
                  -Dsonar.sources=app \
                  -Dsonar.tests=tests \
                  -Dsonar.python.coverage.reportPaths=coverage.xml \
                  -Dsonar.host.url=${SONAR_HOST_URL} \
                  -Dsonar.token=${SONAR_TOKEN}
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                docker build -t ${APP_NAME}:${APP_VERSION} -f docker/Dockerfile .

                docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${APP_VERSION}
                docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:latest
                docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                '''
            }
        }

        stage('Trivy Scan') {
            steps {
                sh '''
                if command -v trivy > /dev/null 2>&1; then
                    trivy image --severity HIGH,CRITICAL ${APP_NAME}:${APP_VERSION}
                else
                    echo "Trivy not installed"
                fi
                '''
            }
        }

        stage('Container Test') {
            steps {
                sh '''
                docker rm -f ${APP_NAME} || true

                docker run -d -p 5000:5000 \
                    --name ${APP_NAME} \
                    ${APP_NAME}:${APP_VERSION}

                sleep 8

                curl -f http://localhost:5000/health
                curl -f http://localhost:5000/
                curl -f http://localhost:5000/secure
                curl -f http://localhost:5000/metrics
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

        stage('Push Docker Image') {

            when {
                branch 'main'
            }

            steps {

                sh '''
                echo "${DOCKER_CREDS_PSW}" | docker login -u "${DOCKER_CREDS_USR}" --password-stdin

                docker push ${DOCKER_IMAGE}:${APP_VERSION}
                docker push ${DOCKER_IMAGE}:latest
                docker push ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}

                docker logout
                '''
            }
        }

    }

    post {

        always {

            script {
                sh '''
                docker rm -f ${APP_NAME} || true
                docker image prune -f || true
                '''
            }

            cleanWs()
        }

        success {
            echo "================================"
            echo "PIPELINE SUCCESS"
            echo "Image: ${DOCKER_IMAGE}:${APP_VERSION}"
            echo "Commit: ${env.GIT_COMMIT_SHORT}"
            echo "================================"
        }

        failure {
            echo "================================"
            echo "PIPELINE FAILED"
            echo "Build: ${BUILD_NUMBER}"
            echo "================================"
        }
    }
}
