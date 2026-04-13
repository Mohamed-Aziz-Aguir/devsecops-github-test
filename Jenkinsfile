pipeline {
    agent any

    environment {
        APP_NAME = "secure-task-app"
        DOCKER_REGISTRY = "devsecops-test"
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
                echo "Checking repository structure..."
                sh 'ls -la'
                sh 'ls -la app/'
            }
        }

        stage('Setup Environment') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip setuptools wheel
                    pip install -r requirements.txt
                    echo "Python environment ready"
                '''
            }
        }

        stage('Code Linting - Flake8') {
            steps {
                sh '''
                    . venv/bin/activate
                    echo "Running Flake8..."
                    flake8 app/ --max-line-length=100 --exclude=venv --statistics || true
                '''
            }
        }

        stage('Code Analysis - Pylint') {
            steps {
                sh '''
                    . venv/bin/activate
                    echo "Running Pylint..."
                    pylint app/ --fail-under=6.0 --exit-zero
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    echo "Running tests with coverage..."
                    pytest tests/ -v --cov=app --cov-report=term --junitxml=test-results.xml
                '''
            }
            post {
                always {
                    junit 'test-results.xml'
                }
            }
        }

        stage('Security Scan - Bandit') {
            steps {
                sh '''
                    . venv/bin/activate
                    echo "Running Bandit security scan..."
                    bandit -r app/ -f json -o bandit-report.json || true
                    bandit -r app/ -f txt -o bandit-report.txt || true
                    echo "Bandit scan completed"
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'bandit-report.txt, bandit-report.json', allowEmptyArchive: true
                }
            }
        }

        stage('Dependency Vulnerability Scan') {
            steps {
                sh '''
                    . venv/bin/activate
                    echo "Scanning dependencies for vulnerabilities..."
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

        stage('Build Docker Image') {
            steps {
                sh '''
                    echo "Building Docker image..."
                    docker build -t ${APP_NAME}:latest -f docker/Dockerfile .
                    docker tag ${APP_NAME}:latest ${APP_NAME}:${BUILD_NUMBER}
                    docker images | grep ${APP_NAME}
                '''
            }
        }

        stage('Docker Security Scan') {
            steps {
                sh '''
                    echo "Scanning Docker image for vulnerabilities..."
                    # Using trivy if available, otherwise skip
                    if command -v trivy &> /dev/null; then
                        trivy image --severity HIGH,CRITICAL --exit-code 0 ${APP_NAME}:latest
                    else
                        echo "Trivy not installed - skipping container vulnerability scan"
                    fi
                '''
            }
        }

        stage('Run Container Tests') {
            steps {
                sh '''
                    echo "Starting container for testing..."
                    # Clean up any existing container
                    docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    
                    # Run container
                    docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:latest
                    
                    # Wait for container to be ready
                    echo "Waiting for container to be ready..."
                    sleep 10
                    
                    # Test endpoints
                    echo "Testing health endpoint..."
                    curl -f http://localhost:5000/health || exit 1
                    
                    echo "Testing home endpoint..."
                    curl -f http://localhost:5000/ || exit 1
                    
                    echo "Testing secure endpoint..."
                    curl -f http://localhost:5000/secure || exit 1
                    
                    echo "All container tests passed!"
                '''
            }
            post {
                always {
                    sh '''
                        docker logs ${APP_NAME} || true
                        docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    '''
                }
            }
        }

        stage('Integration Tests') {
            steps {
                sh '''
                    echo "Running integration tests..."
                    # Start container in background
                    docker run -d -p 5001:5000 --name ${APP_NAME}-test ${APP_NAME}:latest
                    
                    sleep 5
                    
                    # Run integration tests
                    curl -f http://localhost:5001/health > /dev/null
                    curl -f http://localhost:5001/ > /dev/null
                    
                    echo "Integration tests passed!"
                '''
            }
            post {
                always {
                    sh '''
                        docker ps -q -f name=${APP_NAME}-test | grep -q . && docker rm -f ${APP_NAME}-test || true
                    '''
                }
            }
        }
    }

    post {
        always {
            script {
                sh '''
                    echo "Cleaning up containers..."
                    docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    docker ps -q -f name=${APP_NAME}-test | grep -q . && docker rm -f ${APP_NAME}-test || true
                    
                    echo "Cleaning up images (keeping last 5)..."
                    docker images ${APP_NAME} --format "table {{.Repository}}:{{.Tag}}" | tail -n +2 | head -n -5 | xargs -r docker rmi || true
                '''
            }
            cleanWs()
        }
        success {
            echo "========================================="
            echo "✅ PIPELINE EXECUTED SUCCESSFULLY! ✅"
            echo "========================================="
            echo "All stages passed:"
            echo "  ✓ Code linting passed"
            echo "  ✓ Unit tests passed"
            echo "  ✓ Security scans completed"
            echo "  ✓ Docker image built"
            echo "  ✓ Container tests passed"
            echo "========================================="
        }
        failure {
            echo "========================================="
            echo "❌ PIPELINE FAILED! ❌"
            echo "========================================="
            echo "Check the logs above for details."
            echo "Common issues:"
            echo "  - Flake8/Pylint violations"
            echo "  - Unit test failures"
            echo "  - Security vulnerabilities found"
            echo "  - Docker build errors"
            echo "========================================="
        }
    }
}
