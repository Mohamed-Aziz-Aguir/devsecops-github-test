pipeline {

    agent any

    environment {
        APP_NAME = "secure-task-app"
        IMAGE_NAME = "${APP_NAME}:${BUILD_NUMBER}"
        IMAGE_LATEST = "${APP_NAME}:latest"
    }

    options {
        timestamps()
        timeout(time: 1, unit: 'HOURS')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('Setup Python') {
            steps {
                sh '''
                python3 -m venv venv
                . venv/bin/activate

                pip install --upgrade pip
                pip install -r requirements.txt
                pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Code Quality - Flake8') {
            steps {
                sh '''
                . venv/bin/activate
                flake8 app --max-line-length=120 || true
                '''
            }
        }

        stage('Code Quality - Pylint') {
            steps {
                sh '''
                . venv/bin/activate
                pylint app/app.py --exit-zero
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                . venv/bin/activate
                pytest tests --maxfail=1 --disable-warnings -q
                '''
            }
        }

        stage('SAST - Bandit') {
            steps {
                sh '''
                . venv/bin/activate
                bandit -r app -f txt --exit-zero
                '''
            }
        }

        stage('Dependency Scan - pip-audit') {
            steps {
                sh '''
                . venv/bin/activate
                pip-audit || true
                '''
            }
        }

        stage('SonarQube Scan') {
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh '''
                    sonar-scanner \
                      -Dsonar.projectKey=secure-task-manager \
                      -Dsonar.sources=app \
                      -Dsonar.host.url=http://localhost:9000 \
                      -Dsonar.login=$SONAR_TOKEN
                    '''
                }
            }
        }

        stage('Trivy Filesystem Scan') {
            steps {
                sh '''
                trivy fs . --severity HIGH,CRITICAL --exit-code 0
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                docker build -t $IMAGE_NAME -t $IMAGE_LATEST -f docker/Dockerfile .
                '''
            }
        }

        stage('Trivy Image Scan') {
            steps {
                sh '''
                trivy image $IMAGE_LATEST --severity HIGH,CRITICAL --exit-code 0
                '''
            }
        }

        stage('Run Application') {
            steps {
                sh '''
                docker rm -f $APP_NAME || true

                docker run -d \
                    --name $APP_NAME \
                    -p 5000:5000 \
                    $IMAGE_LATEST

                sleep 10

                curl http://localhost:5000/health
                '''
            }
        }

        stage('DAST - OWASP ZAP') {
            steps {
                sh '''
                docker run --rm \
                    --network=host \
                    ghcr.io/zaproxy/zaproxy:stable \
                    zap-baseline.py \
                    -t http://localhost:5000 \
                    -I
                '''
            }
        }

    }

    post {

        always {
            sh '''
            docker rm -f $APP_NAME || true
            '''
            cleanWs()
        }

        success {
            echo "PIPELINE SUCCESS"
        }

        failure {
            echo "PIPELINE FAILED"
        }
    }
}
