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

        // Add sonar-scanner to PATH
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

        // ========== NEW: SonarQube Analysis + Quality Gate (fixed) ==========
        stage('SonarQube Analysis') {
            when { expression { env.SONAR_TOKEN != null && env.SONAR_TOKEN != '' } }
            steps {
                script {
                    withSonarQubeEnv('sonarqube') {
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
            }
        }

        stage('Quality Gate') {
            when { expression { env.SONAR_TOKEN != null && env.SONAR_TOKEN != '' } }
            steps {
                script {
                    withSonarQubeEnv('sonarqube') {
                        echo "Waiting for SonarQube Quality Gate..."
                        timeout(time: 5, unit: 'MINUTES') {
                            waitForQualityGate abortPipeline: false   // set to true if you want to fail on gate failure
                        }
                    }
                }
            }
        }

        // ========== NEW: Trivy filesystem scan ==========
        stage('Trivy File Scan') {
            steps {
                sh '''
                    echo "Running Trivy filesystem scan on source code..."
                    mkdir -p trivy-reports
                    if command -v trivy > /dev/null 2>&1; then
                        trivy fs . --format json --output trivy-reports/trivy-fs.json || true
                        trivy fs . --format table --output trivy-reports/trivy-fs.txt || true
                        echo "Trivy filesystem scan completed"
                    else
                        echo "Trivy not installed - skipping filesystem scan"
                    fi
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-reports/trivy-fs.*', allowEmptyArchive: true
                }
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

        stage('Trivy Image Scan') {
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
                            --output trivy-reports/trivy-image-high-critical.json \
                            ${APP_NAME}:${APP_VERSION} || true
                        # Full report (all severities)
                        trivy image --format json --output trivy-reports/trivy-image-full.json \
                            ${APP_NAME}:${APP_VERSION} || true
                        echo "Trivy image scan completed"
                    else
                        echo "Trivy not installed - skipping image scan"
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

        // ========== NEW: DAST Scan with OWASP ZAP ==========
        stage('DAST Scan') {
            steps {
                script {
                    echo '🔍 Running OWASP ZAP baseline scan on the Flask app...'

                    // Start a fresh container for ZAP (port 5000 must be free)
                    sh '''
                        docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                        docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:${APP_VERSION}
                        sleep 5
                    '''

                    def zapExitCode = sh(
                        script: '''
                            docker run --rm --user root --network host \
                                -v $(pwd):/zap/wrk:rw \
                                -t zaproxy/zap-stable zap-baseline.py \
                                -t http://localhost:5000 \
                                -r zap_report.html -J zap_report.json || true
                        ''',
                        returnStatus: true
                    )

                    echo "ZAP scan finished with exit code: ${zapExitCode}"

                    if (fileExists('zap_report.json')) {
                        try {
                            def zapJson = readJSON file: 'zap_report.json'
                            def highCount = zapJson.site.collect { site ->
                                site.alerts.findAll { it.risk == 'High' }.size()
                            }.sum() ?: 0
                            def mediumCount = zapJson.site.collect { site ->
                                site.alerts.findAll { it.risk == 'Medium' }.size()
                            }.sum() ?: 0
                            def lowCount = zapJson.site.collect { site ->
                                site.alerts.findAll { it.risk == 'Low' }.size()
                            }.sum() ?: 0

                            echo "✅ High severity issues: ${highCount}"
                            echo "⚠️ Medium severity issues: ${mediumCount}"
                            echo "ℹ️ Low severity issues: ${lowCount}"
                        } catch (Exception e) {
                            echo "Could not parse ZAP report: ${e.message}"
                        }
                    } else {
                        echo "ZAP JSON report not found, continuing build..."
                    }

                    echo "✅ DAST scan completed."
                }
            }
            post {
                always {
                    sh 'docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true'
                    publishHTML([
                        reportDir: '.',
                        reportFiles: 'zap_report.html',
                        reportName: 'OWASP ZAP Report',
                        allowMissing: true,
                        keepAll: true,
                        alwaysLinkToLastBuild: false
                    ])
                    archiveArtifacts artifacts: 'zap_report.html, zap_report.json', allowEmptyArchive: true
                }
            }
        }

        stage('Push to Docker Hub') {
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
    }

    post {
        always {
            script {
                // Collect all security reports into one directory for archiving
                sh '''
                    mkdir -p security-reports
                    cp bandit-report.html bandit-report.json security-reports/ 2>/dev/null || true
                    cp audit-report.json security-reports/ 2>/dev/null || true
                    cp pylint-report.txt security-reports/ 2>/dev/null || true
                    cp trivy-reports/* security-reports/ 2>/dev/null || true
                    cp zap_report.* security-reports/ 2>/dev/null || true
                '''
                archiveArtifacts artifacts: 'security-reports/**', allowEmptyArchive: true
            }
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

            // Email notification on success (requires Email Extension Plugin)
            script {
                def buildUser = currentBuild.getBuildCauses('hudson.model.Cause$UserIdCause')[0]?.userId ?: 'GitHub User'
                emailext(
                    subject: "✅ Pipeline SUCCESS: ${APP_NAME} #${BUILD_NUMBER}",
                    body: """
                        <html>
                            <body style="font-family: Arial, sans-serif;">
                                <h2>DevSecOps Pipeline Report</h2>
                                <hr>
                                <h3>Build Information</h3>
                                <table border="1" cellpadding="10">
                                    <tr><td><b>Job Name</b></td><td>${env.JOB_NAME}</td></tr>
                                    <tr><td><b>Build Number</b></td><td>${env.BUILD_NUMBER}</td></tr>
                                    <tr><td><b>Status</b></td><td style="color:green"><b>SUCCESS</b></td></tr>
                                    <tr><td><b>Started by</b></td><td>${buildUser}</td></tr>
                                    <tr><td><b>Build URL</b></td><td><a href="${env.BUILD_URL}">${env.BUILD_URL}</a></td></tr>
                                </table>
                                <hr>
                                <h3>Security Scans Performed</h3>
                                <ul>
                                    <li>✅ SAST: SonarQube</li>
                                    <li>✅ Bandit (Python)</li>
                                    <li>✅ Dependency: pip-audit</li>
                                    <li>✅ Container: Trivy (image + filesystem)</li>
                                    <li>✅ DAST: OWASP ZAP</li>
                                </ul>
                                <hr>
                                <p>Attached are the security reports.</p>
                            </body>
                        </html>
                    """,
                    to: 'mohamedaziz.aguir@gmail.com',
                    from: 'mohamedaziz.aguir@gmail.com',
                    mimeType: 'text/html',
                    attachmentsPattern: 'security-reports/**'
                )
            }
        }
        failure {
            echo "========================================="
            echo "PIPELINE FAILED - Check logs above"
            echo "Build: ${APP_NAME} #${BUILD_NUMBER}"
            echo "========================================="

            // Email notification on failure
            script {
                def buildUser = currentBuild.getBuildCauses('hudson.model.Cause$UserIdCause')[0]?.userId ?: 'GitHub User'
                emailext(
                    subject: "❌ Pipeline FAILED: ${APP_NAME} #${BUILD_NUMBER}",
                    body: """
                        <html>
                            <body>
                                <h2>Build Failed</h2>
                                <p>Job: ${env.JOB_NAME}<br>
                                Build: ${env.BUILD_NUMBER}<br>
                                Started by: ${buildUser}<br>
                                <a href="${env.BUILD_URL}">Click here for console output</a></p>
                            </body>
                        </html>
                    """,
                    to: 'mohamedaziz.aguir@gmail.com',
                    from: 'mohamedaziz.aguir@gmail.com',
                    mimeType: 'text/html'
                )
            }
        }
    }
}
