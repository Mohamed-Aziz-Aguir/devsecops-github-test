pipeline {
    agent any

    environment {
        SONAR_HOST_URL = "http://localhost:9000"
    }

    stages {

        stage('SonarQube Analysis') {
            steps {
                withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
                    sh """
                    sonar-scanner \
                      -Dsonar.projectKey=devsecops-test \
                      -Dsonar.sources=. \
                      -Dsonar.host.url=$SONAR_HOST_URL \
                      -Dsonar.login=$SONAR_TOKEN
                    """
                }
            }
        }
    }
}
