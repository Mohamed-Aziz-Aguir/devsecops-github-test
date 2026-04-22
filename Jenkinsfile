pipeline {
    agent any

    environment {
        APP_NAME         = "secure-task-app"
        APP_VERSION      = "1.0.${BUILD_NUMBER}"
        DOCKER_REGISTRY  = "docker.io"
        DOCKER_NAMESPACE = "mohamedazizaguir"
        DOCKER_IMAGE     = "${DOCKER_REGISTRY}/${DOCKER_NAMESPACE}/${APP_NAME}"
        PYTHONPATH       = "${env.WORKSPACE}"

        SONAR_HOST_URL   = "http://192.168.119.130:9000"
        SONAR_TOKEN      = credentials('sonar-token')
        DOCKER_CREDS     = credentials('Docker-Hub')

        PATH             = "/opt/sonar-scanner/bin:${env.PATH}"
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '5'))
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
                echo "Building ${APP_NAME} - Version: ${APP_VERSION} - Build #${BUILD_NUMBER}"
                script {
                    def gitCommit = sh(script: 'git rev-parse --short HEAD 2>/dev/null || echo "unknown"', returnStdout: true).trim()
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
                    pip install --upgrade pip --quiet
                    pip install -r requirements-dev.txt --quiet
                '''
            }
        }

        stage('Lint') {
            parallel {
                stage('Flake8') {
                    steps {
                        sh '. venv/bin/activate && flake8 app/ --max-line-length=100 --statistics --count || true'
                    }
                }
                stage('Pylint') {
                    steps {
                        sh '. venv/bin/activate && pylint app/ --fail-under=6.0 --exit-zero --output-format=parseable > pylint-report.txt || true'
                    }
                    post {
                        always { archiveArtifacts artifacts: 'pylint-report.txt', allowEmptyArchive: true }
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
                    junit testResults: 'test-results.xml', allowEmptyResults: true
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
                        always { archiveArtifacts artifacts: 'audit-report.json', allowEmptyArchive: true }
                    }
                }
            }
        }

        stage('SonarQube Analysis') {
            when { expression { env.SONAR_TOKEN != null && env.SONAR_TOKEN != '' } }
            steps {
                script {
                    withSonarQubeEnv('sonarqube') {
                        sh '''
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
                                -Dsonar.token=${SONAR_TOKEN}
                        '''

                        def taskId = sh(script: 'grep -m1 "^ceTaskId=" .scannerwork/report-task.txt 2>/dev/null | cut -d= -f2 || echo ""', returnStdout: true).trim()
                        if (!taskId) error "Failed to retrieve SonarQube CE task ID."
                        echo "SonarQube CE task ID: ${taskId}"
                        writeFile file: 'sonar-task-id.txt', text: taskId
                        stash name: 'sonar-task-id', includes: 'sonar-task-id.txt'
                    }
                }
            }
        }

        stage('Quality Gate') {
            when { expression { env.SONAR_TOKEN != null && env.SONAR_TOKEN != '' } }
            steps {
                script {
                    unstash 'sonar-task-id'
                    def taskId = readFile('sonar-task-id.txt').trim()
                    echo "Waiting for quality gate for task: ${taskId}"

                    def maxAttempts = 20
                    def taskSuccess = false
                    for (int i = 0; i < maxAttempts; i++) {
                        def status = sh(script: "curl -s -u ${SONAR_TOKEN}: \"${SONAR_HOST_URL}/api/ce/task?id=${taskId}\" | grep -o '\"status\":\"[^\"]*\"' | head -1 | cut -d'\"' -f4", returnStdout: true).trim()
                        echo "CE task status (${i+1}/${maxAttempts}): ${status}"

                        if (status == 'SUCCESS') {
                            taskSuccess = true
                            break
                        } else if (status == 'FAILED' || status == 'CANCELLED') {
                            error "SonarQube analysis task ${status}."
                        }
                        sleep 5
                    }
                    if (!taskSuccess) error "Timed out waiting for SonarQube analysis (10 minutes)."

                    def gateStatus = sh(script: "curl -s -u ${SONAR_TOKEN}: \"${SONAR_HOST_URL}/api/qualitygates/project_status?projectKey=${APP_NAME}\" | grep -o '\"status\":\"[^\"]*\"' | head -1 | cut -d'\"' -f4", returnStdout: true).trim()
                    echo "Quality Gate status: ${gateStatus}"
                    if (gateStatus != 'OK') error "Quality Gate FAILED. Check ${SONAR_HOST_URL}/dashboard?id=${APP_NAME}"
                }
            }
        }

        stage('Trivy File Scan') {
            steps {
                sh '''
                    mkdir -p trivy-reports
                    if command -v trivy > /dev/null 2>&1; then
                        trivy fs . --format json --output trivy-reports/trivy-fs.json --skip-dirs venv --skip-dirs .git || true
                        trivy fs . --format table --output trivy-reports/trivy-fs.txt --skip-dirs venv --skip-dirs .git || true
                    else
                        echo "Trivy not installed – skipping filesystem scan"
                    fi
                '''
            }
            post {
                always { archiveArtifacts artifacts: 'trivy-reports/trivy-fs.*', allowEmptyArchive: true }
                
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    docker build -t ${APP_NAME}:${APP_VERSION} -f docker/Dockerfile .
                    docker tag ${APP_NAME}:${APP_VERSION} ${APP_NAME}:latest
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${APP_VERSION}
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:latest
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                '''
            }
        }

        stage('Trivy Image Scan') {
            steps {
                sh '''
                    mkdir -p trivy-reports
                    if command -v trivy > /dev/null 2>&1; then
                        trivy image --severity HIGH,CRITICAL --format table ${APP_NAME}:${APP_VERSION} || true
                        trivy image --severity HIGH,CRITICAL --format json --output trivy-reports/trivy-image-high-critical.json ${APP_NAME}:${APP_VERSION} || true
                        trivy image --format json --output trivy-reports/trivy-image-full.json ${APP_NAME}:${APP_VERSION} || true
                    else
                        echo "Trivy not installed – skipping image scan"
                    fi
                '''
            }
            post {
                always { archiveArtifacts artifacts: 'trivy-reports/*', allowEmptyArchive: true }
            }
        }

        stage('Docker Container Test') {
            steps {
                sh '''
                    docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                    docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:${APP_VERSION}
                    for i in $(seq 1 12); do
                        curl -sf http://localhost:5000/health > /dev/null && echo "App is up (attempt ${i})" && break
                        echo "Waiting for app... (${i}/12)"; sleep 3
                    done
                    curl -f http://localhost:5000/health
                    curl -f http://localhost:5000/
                    curl -f http://localhost:5000/metrics
                '''
            }
            post {
                always {
                    sh 'docker logs ${APP_NAME} 2>/dev/null || true'
                    sh 'docker rm -f ${APP_NAME} 2>/dev/null || true'
                }
            }
        }

        stage('DAST Scan') {
            steps {
                script {
                    sh '''
                        docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                        docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:${APP_VERSION}
                        for i in $(seq 1 12); do
                            curl -sf http://localhost:5000/health > /dev/null && echo "App ready (${i})" && break
                            echo "Waiting for app... (${i}/12)"; sleep 3
                        done
                    '''

                    def zapExitCode = sh(script: '''
                        docker run --rm --user root --network host \
                            -v $(pwd):/zap/wrk:rw \
                            -t zaproxy/zap-stable zap-baseline.py \
                            -t http://localhost:5000 \
                            -r zap_report.html -J zap_report.json || true
                    ''', returnStatus: true)
                    echo "ZAP scan finished with exit code: ${zapExitCode}"

                    if (fileExists('zap_report.json')) {
                        def highCount = sh(script: 'grep -o \'"risk":"High"\' zap_report.json | wc -l || echo 0', returnStdout: true).trim()
                        def mediumCount = sh(script: 'grep -o \'"risk":"Medium"\' zap_report.json | wc -l || echo 0', returnStdout: true).trim()
                        def lowCount = sh(script: 'grep -o \'"risk":"Low"\' zap_report.json | wc -l || echo 0', returnStdout: true).trim()
                        echo "High: ${highCount} | Medium: ${mediumCount} | Low: ${lowCount}"
                    }
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
        stage('Deploy to Minikube') {
    steps {
        sh '''
            kubectl config use-context minikube
            kubectl create namespace devsecops --dry-run=client -o yaml | kubectl apply -f -

            # Replace image tag with actual version
            export IMAGE_TAG=${APP_VERSION}
            envsubst < k8s/deployment.yaml | kubectl apply -f - -n devsecops

            kubectl apply -f k8s/service.yaml -n devsecops
            kubectl rollout status deployment/${APP_NAME} -n devsecops
        '''
    }
}
stage('Falco Runtime Security Scan') {
    steps {
        script {
            // Start the app container for Falco to monitor
            sh '''
                docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                docker run -d -p 5000:5000 --name ${APP_NAME} ${APP_NAME}:${APP_VERSION}
                for i in $(seq 1 12); do
                    curl -sf http://localhost:5000/health > /dev/null && echo "App ready (${i})" && break
                    echo "Waiting for app... (${i}/12)"; sleep 3
                done
            '''

            // Start Falco in background, monitoring for 60 seconds
            sh '''
                mkdir -p falco-reports
                mkdir -p /tmp/falco-logs

                docker run -d --name falco-scanner \
                    --privileged \
                    --pid=host \
                    -v /var/run/docker.sock:/host/var/run/docker.sock \
                    -v /proc:/host/proc:ro \
                    -v /boot:/host/boot:ro \
                    -v /lib/modules:/host/lib/modules:ro \
                    -v /usr:/host/usr:ro \
                    -v /etc:/host/etc:ro \
                    -v $(pwd)/falco/custom_rules.yaml:/etc/falco/rules.d/custom_rules.yaml:ro \
                    -v $(pwd)/falco/falco.yaml:/etc/falco/falco.yaml:ro \
                    -v /tmp/falco-logs:/var/log/falco \
                    falcosecurity/falco-no-driver:latest

                echo "Falco started, running for 60 seconds while exercising the app..."
                sleep 5

                # Exercise the app to trigger potential rule matches
                curl -sf http://localhost:5000/ || true
                curl -sf http://localhost:5000/health || true
                curl -sf http://localhost:5000/metrics || true

                sleep 55

                # Collect Falco alerts
                docker logs falco-scanner > falco-reports/falco-output.log 2>&1 || true
                cp /tmp/falco-logs/falco-alerts.log falco-reports/falco-alerts.json 2>/dev/null || true

                docker stop falco-scanner || true
                docker rm falco-scanner || true
            '''

            // Parse and evaluate results
            sh '''
                echo "=== Falco Alert Summary ==="
                if [ -f falco-reports/falco-output.log ]; then
                    CRITICAL=$(grep -c '"priority":"Critical"' falco-reports/falco-output.log || echo 0)
                    ERROR=$(grep -c '"priority":"Error"' falco-reports/falco-output.log || echo 0)
                    WARNING=$(grep -c '"priority":"Warning"' falco-reports/falco-output.log || echo 0)
                    echo "Critical: ${CRITICAL} | Error: ${ERROR} | Warning: ${WARNING}"

                    if [ "${CRITICAL}" -gt 0 ]; then
                        echo "CRITICAL Falco alerts detected:"
                        grep '"priority":"Critical"' falco-reports/falco-output.log || true
                    fi
                else
                    echo "No Falco output found"
                fi
            '''

            // Fail build on CRITICAL alerts (optional — change to WARNING to be strict)
            script {
                def criticalCount = sh(
                    script: 'grep -c \'"priority":"Critical"\' falco-reports/falco-output.log 2>/dev/null || echo 0',
                    returnStdout: true
                ).trim().toInteger()

                if (criticalCount > 0) {
                    error "Falco detected ${criticalCount} CRITICAL runtime security alert(s). Failing build."
                }
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'falco-reports/**', allowEmptyArchive: true
            sh 'docker stop falco-scanner 2>/dev/null || true'
            sh 'docker rm falco-scanner 2>/dev/null || true'
            sh 'docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true'
        }
    }
}
    }

    post {
        always {
            script {
                sh '''
                    mkdir -p security-reports
                    for f in bandit-report.html bandit-report.json audit-report.json pylint-report.txt zap_report.html zap_report.json; do
                        [ -f "$f" ] && cp "$f" security-reports/ || true
                    done
                    [ -d trivy-reports ] && cp trivy-reports/* security-reports/ 2>/dev/null || true
                    [ -d falco-reports ] && cp falco-reports/* security-reports/ 2>/dev/null || true

                '''
                archiveArtifacts artifacts: 'security-reports/**', allowEmptyArchive: true
            }
        }
        success {
            script {
                def buildUser = currentBuild.getBuildCauses('hudson.model.Cause$UserIdCause')[0]?.userId ?: 'GitHub Push'
                emailext(
                    subject: "✅ SUCCESS: ${APP_NAME} #${BUILD_NUMBER}",
                    body: """
                        <html><body style="font-family:Arial,sans-serif;">
                        <h2>DevSecOps Pipeline — SUCCESS</h2><hr>
                        <table border="1" cellpadding="8">
                            <tr><td><b>Job</b></td><td>${env.JOB_NAME}</td></tr>
                            <tr><td><b>Build</b></td><td>${env.BUILD_NUMBER}</td></tr>
                            <tr><td><b>Status</b></td><td style="color:green"><b>SUCCESS</b></td></tr>
                            <tr><td><b>Triggered by</b></td><td>${buildUser}</td></tr>
                            <tr><td><b>Commit</b></td><td>${env.GIT_COMMIT_SHORT}</td></tr>
                            <tr><td><b>URL</b></td><td><a href="${env.BUILD_URL}">${env.BUILD_URL}</a></td></tr>
                        </table><hr>
                        <h3>Security Scans</h3>
                        <ul>
                            <li>SAST: SonarQube + Quality Gate</li>
                            <li>Bandit (Python)</li>
                            <li>pip-audit (dependencies)</li>
                            <li>Trivy (filesystem + image)</li>
                            <li>DAST: OWASP ZAP</li>
                            <li>Falco Runtime Security Scan (custom rules)</li>
                        </ul>
                        <p>Attached: all security reports.</p>
                        </body></html>
                    """,
                    to: 'mohamedaziz.aguir@gmail.com',
                    from: 'mohamedaziz.aguir@gmail.com',
                    mimeType: 'text/html',
                    attachmentsPattern: 'security-reports/**'
                )
            }
            sh '''
                docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                docker images --filter "reference=${APP_NAME}" --format "{{.CreatedAt}}\t{{.Repository}}:{{.Tag}}" | sort -r | tail -n +6 | awk -F'\t' '{print $2}' | xargs -r docker rmi 2>/dev/null || true
            '''
            cleanWs()
        }
        failure {
            script {
                def buildUser = currentBuild.getBuildCauses('hudson.model.Cause$UserIdCause')[0]?.userId ?: 'GitHub Push'
                emailext(
                    subject: "❌ FAILED: ${APP_NAME} #${BUILD_NUMBER}",
                    body: "<html><body><h2>Build Failed</h2><p>Job: ${env.JOB_NAME}<br>Build: ${env.BUILD_NUMBER}<br>Triggered by: ${buildUser}<br><a href='${env.BUILD_URL}console'>Console output</a></p></body></html>",
                    to: 'mohamedaziz.aguir@gmail.com',
                    from: 'mohamedaziz.aguir@gmail.com',
                    mimeType: 'text/html'
                )
            }
            sh '''
                docker ps -q -f name=${APP_NAME} | grep -q . && docker rm -f ${APP_NAME} || true
                docker images --filter "reference=${APP_NAME}" --format "{{.CreatedAt}}\t{{.Repository}}:{{.Tag}}" | sort -r | tail -n +6 | awk -F'\t' '{print $2}' | xargs -r docker rmi 2>/dev/null || true
            '''
            cleanWs()
        }
    }
}
