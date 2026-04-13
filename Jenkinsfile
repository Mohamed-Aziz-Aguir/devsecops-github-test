pipeline {
    agent any

    environment {
        APP_NAME = "secure-task-app"
        IMAGE_TAG = "${BUILD_NUMBER}"
        IMAGE_LATEST = "latest"

        SONAR_HOST_URL = "http://localhost:9000"
        SONAR_PROJECT_KEY = "secure-task-manager"

        VENV = "venv"

        TRIVY_SEVERITY = "HIGH,CRITICAL"
    }

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 1, unit: 'HOURS')
    }

    stages {

        stage('📥 Checkout') {
            steps {
                checkout scm
                sh "git log -1 --oneline"
            }
        }

        stage('🐍 Setup Python Environment') {
            steps {
                sh """
                    python3 -m venv ${VENV}
                    . ${VENV}/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt

                    pip install flake8 pylint bandit pip-audit
                """
            }
        }

        stage('🎨 Code Quality - Flake8') {
            steps {
                sh """
                    . ${VENV}/bin/activate
                    flake8 . --max-line-length=120 --exit-zero
                """
            }
        }

        stage('🎨 Code Quality - Pylint') {
            steps {
                sh """
                    . ${VENV}/bin/activate
                    pylint app.py --exit-zero
                """
            }
        }

        stage('🔐 SAST - Bandit') {
            steps {
                sh """
                    . ${VENV}/bin/activate
                    bandit -r . -f txt --exit-zero
                """
            }
        }

        stage('📦 Dependency Scan - pip-audit') {
            steps {
                sh """
                    . ${VENV}/bin/activate
                    pip-audit || true
                """
            }
        }

        stage('📊 SonarQube Analysis') {
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh """
                        sonar-scanner \
                        -Dsonar.projectKey=${SONAR_PROJECT_KEY} \
                        -Dsonar.sources=. \
                        -Dsonar.host.url=${SONAR_HOST_URL} \
                        -Dsonar.login=$SONAR_TOKEN
                    """
                }
            }
        }

        stage('🔎 Trivy FS Scan') {
            steps {
                sh """
                    trivy fs . --severity ${TRIVY_SEVERITY} || true
                """
            }
        }

        stage('🐳 Docker Build') {
            steps {
                sh """
                    docker build \
                        -t ${APP_NAME}:${IMAGE_TAG} \
                        -t ${APP_NAME}:${IMAGE_LATEST} .
                """
            }
        }

        stage('🛡️ Trivy Image Scan') {
            steps {
                sh """
                    trivy image ${APP_NAME}:${IMAGE_LATEST} || true
                """
            }
        }

        stage('🚀 Run Application') {
            steps {
                sh """
                    docker rm -f ${APP_NAME} || true

                    docker run -d \
                        --name ${APP_NAME} \
                        -p 5000:5000 \
                        ${APP_NAME}:${IMAGE_LATEST}

                    sleep 5
                    curl -f http://localhost:5000 || true
                """
            }
        }

        stage('🕷️ OWASP ZAP (DAST)') {
            steps {
                sh """
                    docker run --rm \
                        --network=host \
                        -v \$(pwd):/zap/wrk/:rw \
                        ghcr.io/zaproxy/zaproxy:stable \
                        zap-baseline.py \
                        -t http://localhost:5000 \
                        -r zap-report.html || true
                """
            }
        }
    }

    post {

        always {
            sh "docker rm -f ${APP_NAME} || true"
            cleanWs()
        }

        success {
            echo "✅ PIPELINE SUCCESS - BUILD ${BUILD_NUMBER}"
        }

        failure {
            echo "❌ PIPELINE FAILED - CHECK LOGS"
        }
    }
}
