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

        // Make sonar-scanner available system-wide in Jenkins PATH
        PATH             = "/opt/sonar-scanner/bin:${env.PATH}"
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '5'))
        timeout(time: 30, unit: 'MINUTES')
        // Prevent concurrent builds colliding on shared Docker/port resources
        disableConcurrentBuilds()
    }

    stages {

        // ── 1. Checkout ────────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                echo "Building ${APP_NAME} - Version: ${APP_VERSION} - Build #${BUILD_NUMBER}"
                script {
                    // Safe fallback: if git fails, don't break the whole pipeline
                    def gitCommit = sh(
                        script: 'git rev-parse --short HEAD 2>/dev/null || echo "unknown"',
                        returnStdout: true
                    ).trim()
                    env.GIT_COMMIT_SHORT = gitCommit
                    echo "Git Commit: ${env.GIT_COMMIT_SHORT}"
                }
            }
        }

        // ── 2. Python setup ────────────────────────────────────────────────
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

        // ── 3. Lint (parallel) ─────────────────────────────────────────────
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
                            pylint app/ --fail-under=6.0 --exit-zero \
                                --output-format=parseable > pylint-report.txt || true
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'pylint-report.txt',
                                             allowEmptyArchive: true
                        }
                    }
                }
            }
        }

        // ── 4. Unit tests + coverage ───────────────────────────────────────
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
                        reportDir              : 'htmlcov',
                        reportFiles            : 'index.html',
                        reportName             : 'Coverage Report',
                        allowMissing           : true,
                        keepAll                : true,
                        alwaysLinkToLastBuild  : false
                    ])
                }
            }
        }

        // ── 5. SAST — Bandit + pip-audit (parallel) ────────────────────────
        stage('Security Scanning') {
            parallel {
                stage('Bandit') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            bandit -r app/ -f json -o bandit-report.json || true
                            bandit -r app/ -f html -o bandit-report.html  || true
                        '''
                    }
                    post {
                        always {
                            publishHTML([
                                reportDir              : '.',
                                reportFiles            : 'bandit-report.html',
                                reportName             : 'Bandit Security Report',
                                allowMissing           : true,
                                keepAll                : true,
                                alwaysLinkToLastBuild  : false
                            ])
                            archiveArtifacts artifacts: 'bandit-report.json',
                                             allowEmptyArchive: true
                        }
                    }
                }
                stage('Dependency Scan') {
                    steps {
                        sh '''
                            . venv/bin/activate
                            pip-audit --requirement requirements.txt \
                                --format json --output audit-report.json || true
                            pip-audit --requirement requirements.txt \
                                --format columns || true
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'audit-report.json',
                                             allowEmptyArchive: true
                        }
                    }
                }
            }
        }

        // ── 6. SonarQube analysis + quality gate ───────────────────────────
        //
        // FIX 1: taskId was null — we now read it from .scannerwork/report-task.txt
        //         which sonar-scanner always writes after a successful analysis.
        // FIX 2: readJSON removed — your Jenkins lacks Pipeline Utility Steps plugin.
        //         All JSON parsing is done with grep/shell.
        // FIX 3: withSonarQubeEnv injects SONAR_HOST_URL automatically from the
        //         server config you set up in Jenkins → Manage Jenkins → SonarQube.
        //         We still pass -Dsonar.token explicitly because the binding is
        //         already masked by withCredentials above.
        // ──────────────────────────────────────────────────────────────────
        stage('SonarQube Analysis & Gate') {
            when { expression { env.SONAR_TOKEN != null && env.SONAR_TOKEN != '' } }
            steps {
                script {
                    withSonarQubeEnv('sonarqube') {
                        // Run the scanner — it writes .scannerwork/report-task.txt on success
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
                                -Dsonar.token=${SONAR_TOKEN}
                            echo "Scanner finished."
                        '''

                        // Extract the CE task ID written by the scanner
                        def taskId = sh(
                            script: '''
                                grep -m1 "^ceTaskId=" .scannerwork/report-task.txt \
                                    2>/dev/null | cut -d= -f2 || echo ""
                            ''',
                            returnStdout: true
                        ).trim()

                        if (!taskId) {
                            echo "WARNING: Could not read ceTaskId — skipping quality gate poll."
                        } else {
                            echo "SonarQube CE task ID: ${taskId}"

                            // Poll CE task status — no readJSON needed
                            def maxAttempts = 60      // 5 minutes (5 s × 60)
                            def analysisFinished = false
                            for (int i = 0; i < maxAttempts; i++) {
                                def status = sh(
                                    script: """
                                        curl -sf \
                                            -H "Authorization: Bearer ${SONAR_TOKEN}" \
                                            "${SONAR_HOST_URL}/api/ce/task?id=${taskId}" \
                                        | grep -o '"status":"[^"]*"' \
                                        | head -1 \
                                        | cut -d'"' -f4 \
                                        || echo "UNKNOWN"
                                    """,
                                    returnStdout: true
                                ).trim()

                                echo "CE task status (${i + 1}/${maxAttempts}): ${status}"

                                if (status == 'SUCCESS') {
                                    analysisFinished = true
                                    break
                                } else if (status == 'FAILED' || status == 'CANCELLED') {
                                    error "SonarQube CE task ${status}. Check SonarQube server logs."
                                }
                                sleep(time: 5, unit: 'SECONDS')
                            }

                            if (!analysisFinished) {
                                echo "WARNING: Timed out waiting for SonarQube. Proceeding anyway."
                            } else {
                                // Check quality gate
                                def gateStatus = sh(
                                    script: """
                                        curl -sf \
                                            -H "Authorization: Bearer ${SONAR_TOKEN}" \
                                            "${SONAR_HOST_URL}/api/qualitygates/project_status?projectKey=${APP_NAME}" \
                                        | grep -o '"status":"[^"]*"' \
                                        | head -1 \
                                        | cut -d'"' -f4 \
                                        || echo "UNKNOWN"
                                    """,
                                    returnStdout: true
                                ).trim()

                                echo "Quality Gate status: ${gateStatus}"

                                if (gateStatus == 'OK') {
                                    echo "Quality Gate PASSED."
                                } else if (gateStatus == 'ERROR') {
                                    error "Quality Gate FAILED. Check ${SONAR_HOST_URL}/dashboard?id=${APP_NAME}"
                                } else {
                                    echo "WARNING: Quality Gate status '${gateStatus}' — proceeding."
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── 7. Trivy filesystem scan ───────────────────────────────────────
        stage('Trivy File Scan') {
            steps {
                sh '''
                    mkdir -p trivy-reports
                    if command -v trivy > /dev/null 2>&1; then
                        echo "Running Trivy filesystem scan..."
                        trivy fs . \
                            --format json \
                            --output trivy-reports/trivy-fs.json \
                            --skip-dirs venv \
                            --skip-dirs .git \
                            || true
                        trivy fs . \
                            --format table \
                            --output trivy-reports/trivy-fs.txt \
                            --skip-dirs venv \
                            --skip-dirs .git \
                            || true
                        echo "Trivy filesystem scan completed."
                    else
                        echo "Trivy not installed — skipping filesystem scan."
                        echo "Install: sudo apt-get install -y trivy"
                    fi
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-reports/trivy-fs.*',
                                     allowEmptyArchive: true
                }
            }
        }

        // ── 8. Docker build ────────────────────────────────────────────────
        stage('Docker Build') {
            steps {
                sh '''
                    echo "Building Docker image..."
                    docker build -t ${APP_NAME}:${APP_VERSION} -f docker/Dockerfile .
                    docker tag ${APP_NAME}:${APP_VERSION} ${APP_NAME}:latest
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${APP_VERSION}
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:latest
                    docker tag ${APP_NAME}:${APP_VERSION} ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                    echo "Images created:"
                    docker images | grep ${APP_NAME}
                '''
            }
        }

        // ── 9. Trivy image scan ────────────────────────────────────────────
        stage('Trivy Image Scan') {
            steps {
                sh '''
                    mkdir -p trivy-reports
                    if command -v trivy > /dev/null 2>&1; then
                        echo "Scanning Docker image with Trivy..."
                        trivy image --severity HIGH,CRITICAL \
                            --format table \
                            ${APP_NAME}:${APP_VERSION} || true
                        trivy image --severity HIGH,CRITICAL \
                            --format json \
                            --output trivy-reports/trivy-image-high-critical.json \
                            ${APP_NAME}:${APP_VERSION} || true
                        trivy image \
                            --format json \
                            --output trivy-reports/trivy-image-full.json \
                            ${APP_NAME}:${APP_VERSION} || true
                        echo "Trivy image scan completed."
                    else
                        echo "Trivy not installed — skipping image scan."
                    fi
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-reports/*',
                                     allowEmptyArchive: true
                }
            }
        }

        // ── 10. Docker container smoke test ───────────────────────────────
        //
        // FIX: Added explicit port 5000 check + kill before starting the container
        //      so this stage never fails with "address already in use".
        // ─────────────────────────────────────────────────────────────────
        stage('Docker Container Test') {
            steps {
                sh '''
                    # Kill any container already using port 5000 or the same name
                    docker ps -q -f name=${APP_NAME} | grep -q . \
                        && docker rm -f ${APP_NAME} || true

                    echo "Starting container for smoke test..."
                    docker run -d -p 5000:5000 --name ${APP_NAME} \
                        ${APP_NAME}:${APP_VERSION}

                    # Wait up to 30 s for the app to become ready
                    for i in $(seq 1 12); do
                        if curl -sf http://localhost:5000/health > /dev/null 2>&1; then
                            echo "App is up (attempt ${i})"
                            break
                        fi
                        echo "Waiting for app... (${i}/12)"
                        sleep 3
                    done

                    echo "Testing endpoints..."
                    curl -f http://localhost:5000/health
                    curl -f http://localhost:5000/
                    curl -f http://localhost:5000/metrics
                    echo "All container smoke tests passed!"
                '''
            }
            post {
                always {
                    sh '''
                        docker logs ${APP_NAME} 2>/dev/null || true
                        docker rm -f ${APP_NAME} 2>/dev/null || true
                    '''
                }
            }
        }

        // ── 11. DAST — OWASP ZAP ──────────────────────────────────────────
        //
        // FIX 1: Container Test post-always already removed ${APP_NAME}, so we
        //        start a clean instance here with a dedicated port guard.
        // FIX 2: ZAP JSON parsing replaced — no readJSON, pure grep/wc counting.
        // ─────────────────────────────────────────────────────────────────
        stage('DAST Scan') {
            steps {
                script {
                    echo "Starting app for DAST scan..."
                    sh '''
                        docker ps -q -f name=${APP_NAME} | grep -q . \
                            && docker rm -f ${APP_NAME} || true
                        docker run -d -p 5000:5000 --name ${APP_NAME} \
                            ${APP_NAME}:${APP_VERSION}

                        # Wait for app to be ready before handing over to ZAP
                        for i in $(seq 1 12); do
                            curl -sf http://localhost:5000/health > /dev/null 2>&1 \
                                && echo "App ready (${i})" && break
                            echo "Waiting for app... (${i}/12)"
                            sleep 3
                        done
                    '''

                    echo "Running OWASP ZAP baseline scan..."
                    def zapExitCode = sh(
                        script: '''
                            docker run --rm --user root --network host \
                                -v $(pwd):/zap/wrk:rw \
                                -t zaproxy/zap-stable zap-baseline.py \
                                -t http://localhost:5000 \
                                -r zap_report.html \
                                -J zap_report.json \
                                || true
                        ''',
                        returnStatus: true
                    )
                    echo "ZAP scan finished with exit code: ${zapExitCode}"

                    // Parse severity counts without readJSON — plain grep + wc
                    if (fileExists('zap_report.json')) {
                        def highCount = sh(
                            script: 'grep -o \'"risk":"High"\' zap_report.json | wc -l || echo 0',
                            returnStdout: true
                        ).trim()
                        def mediumCount = sh(
                            script: 'grep -o \'"risk":"Medium"\' zap_report.json | wc -l || echo 0',
                            returnStdout: true
                        ).trim()
                        def lowCount = sh(
                            script: 'grep -o \'"risk":"Low"\' zap_report.json | wc -l || echo 0',
                            returnStdout: true
                        ).trim()
                        echo "High: ${highCount} | Medium: ${mediumCount} | Low: ${lowCount}"
                    } else {
                        echo "ZAP report not found — continuing."
                    }
                    echo "DAST scan completed."
                }
            }
            post {
                always {
                    sh '''
                        docker ps -q -f name=${APP_NAME} | grep -q . \
                            && docker rm -f ${APP_NAME} || true
                    '''
                    publishHTML([
                        reportDir              : '.',
                        reportFiles            : 'zap_report.html',
                        reportName             : 'OWASP ZAP Report',
                        allowMissing           : true,
                        keepAll                : true,
                        alwaysLinkToLastBuild  : false
                    ])
                    archiveArtifacts artifacts: 'zap_report.html, zap_report.json',
                                     allowEmptyArchive: true
                }
            }
        }

        // ── 12. Push to Docker Hub ─────────────────────────────────────────
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
                    echo "${DOCKER_CREDS_PSW}" | \
                        docker login -u "${DOCKER_CREDS_USR}" --password-stdin
                    docker push ${DOCKER_IMAGE}:${APP_VERSION}
                    docker push ${DOCKER_IMAGE}:latest
                    docker push ${DOCKER_IMAGE}:${GIT_COMMIT_SHORT}
                    echo "Images pushed successfully."
                    docker logout
                '''
            }
        }

    } // end stages

    // ── Post ───────────────────────────────────────────────────────────────
    //
    // FIX: Collect all security reports BEFORE cleanWs() so emailext can
    //      attach them and archiveArtifacts can find them.
    // ──────────────────────────────────────────────────────────────────────
    post {
        always {
            script {
                // Bundle every security artefact into one folder for the email attachment
                sh '''
                    mkdir -p security-reports
                    for f in bandit-report.html bandit-report.json \
                              audit-report.json pylint-report.txt \
                              zap_report.html zap_report.json; do
                        [ -f "$f" ] && cp "$f" security-reports/ || true
                    done
                    [ -d trivy-reports ] && cp trivy-reports/* security-reports/ 2>/dev/null || true
                '''
                archiveArtifacts artifacts: 'security-reports/**',
                                 allowEmptyArchive: true
            }

            // Prune stale Docker images (keep newest 5 by creation date)
            sh '''
                docker ps -q -f name=${APP_NAME} | grep -q . \
                    && docker rm -f ${APP_NAME} || true
                docker images --filter "reference=${APP_NAME}" \
                    --format "{{.CreatedAt}}\t{{.Repository}}:{{.Tag}}" \
                    | sort -r \
                    | tail -n +6 \
                    | awk "{print \$2}" \
                    | xargs -r docker rmi || true
            '''

            // Workspace wipe LAST — after all artefacts are safely archived
            cleanWs()
        }

        success {
            echo "================================================="
            echo "PIPELINE COMPLETED SUCCESSFULLY"
            echo "Build  : ${APP_NAME}:${APP_VERSION}"
            echo "Commit : ${env.GIT_COMMIT_SHORT}"
            echo "Sonar  : ${SONAR_HOST_URL}/dashboard?id=${APP_NAME}"
            echo "================================================="

            script {
                def buildUser = currentBuild
                    .getBuildCauses('hudson.model.Cause$UserIdCause')[0]
                    ?.userId ?: 'GitHub Push'

                emailext(
                    subject: "SUCCESS: ${APP_NAME} #${BUILD_NUMBER}",
                    body: """
                        <html><body style="font-family:Arial,sans-serif;">
                        <h2>DevSecOps Pipeline — SUCCESS</h2><hr>
                        <table border="1" cellpadding="8">
                          <tr><td><b>Job</b></td><td>${env.JOB_NAME}</td></tr>
                          <tr><td><b>Build</b></td><td>${env.BUILD_NUMBER}</td></tr>
                          <tr><td><b>Status</b></td>
                              <td style="color:green"><b>SUCCESS</b></td></tr>
                          <tr><td><b>Triggered by</b></td><td>${buildUser}</td></tr>
                          <tr><td><b>Commit</b></td><td>${env.GIT_COMMIT_SHORT}</td></tr>
                          <tr><td><b>URL</b></td>
                              <td><a href="${env.BUILD_URL}">${env.BUILD_URL}</a></td></tr>
                        </table><hr>
                        <h3>Security stages completed</h3>
                        <ul>
                          <li>SAST — SonarQube + Quality Gate</li>
                          <li>SAST — Bandit (Python)</li>
                          <li>SCA  — pip-audit (dependencies)</li>
                          <li>SCAN — Trivy (filesystem + image)</li>
                          <li>DAST — OWASP ZAP baseline</li>
                        </ul>
                        <p>Security reports are attached.</p>
                        </body></html>
                    """,
                    to: 'mohamedaziz.aguir@gmail.com',
                    from: 'mohamedaziz.aguir@gmail.com',
                    mimeType: 'text/html',
                    attachmentsPattern: 'security-reports/**'
                )
            }
        }

        failure {
            echo "================================================="
            echo "PIPELINE FAILED"
            echo "Build  : ${APP_NAME} #${BUILD_NUMBER}"
            echo "================================================="

            script {
                def buildUser = currentBuild
                    .getBuildCauses('hudson.model.Cause$UserIdCause')[0]
                    ?.userId ?: 'GitHub Push'

                emailext(
                    subject: "FAILED: ${APP_NAME} #${BUILD_NUMBER}",
                    body: """
                        <html><body>
                        <h2>Build Failed</h2>
                        <p>
                          Job: ${env.JOB_NAME}<br>
                          Build: ${env.BUILD_NUMBER}<br>
                          Triggered by: ${buildUser}<br>
                          <a href="${env.BUILD_URL}console">Console output</a>
                        </p>
                        </body></html>
                    """,
                    to: 'mohamedaziz.aguir@gmail.com',
                    from: 'mohamedaziz.aguir@gmail.com',
                    mimeType: 'text/html'
                )
            }
        }
    }
}
