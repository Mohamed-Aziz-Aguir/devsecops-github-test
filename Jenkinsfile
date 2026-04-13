pipeline {
agent any

```
environment {
    IMAGE_NAME = "secure-task-app"
    CONTAINER_NAME = "secure-task-app"
}

options {
    timestamps()
    timeout(time: 60, unit: 'MINUTES')
}

stages {

    stage('Checkout') {
        steps {
            checkout scm
            sh 'git log -1 --oneline'
        }
    }

    stage('Setup Python Environment') {
        steps {
            sh '''
            python3 -m venv venv
            . venv/bin/activate

            pip install --upgrade pip
            pip install -r requirements.txt

            pip install pytest pytest-cov flake8 pylint bandit pip-audit
            '''
        }
    }

    stage('Code Quality - Flake8') {
        steps {
            sh '''
            . venv/bin/activate
            flake8 app/
            '''
        }
    }

    stage('Code Quality - Pylint') {
        steps {
            sh '''
            . venv/bin/activate
            pylint app/ --exit-zero
            '''
        }
    }

    stage('Unit Tests') {
        steps {
            sh '''
            . venv/bin/activate
            pytest tests || true
            '''
        }
    }

    stage('SAST - Bandit') {
        steps {
            sh '''
            . venv/bin/activate
            bandit -r app/
            '''
        }
    }

    stage('Dependency Scan - pip-audit') {
        steps {
            sh '''
            . venv/bin/activate
            pip-audit -r requirements.txt
            '''
        }
    }

    stage('Trivy Filesystem Scan') {
        steps {
            sh 'trivy fs .'
        }
    }

    stage('Docker Build') {
        steps {
            sh '''
            docker build -t $IMAGE_NAME docker/
            '''
        }
    }

    stage('Trivy Image Scan') {
        steps {
            sh '''
            trivy image $IMAGE_NAME
            '''
        }
    }

    stage('Run Application') {
        steps {
            sh '''
            docker rm -f $CONTAINER_NAME || true

            docker run -d \
            -p 5000:5000 \
            --name $CONTAINER_NAME \
            $IMAGE_NAME
            '''
        }
    }

    stage('DAST - OWASP ZAP') {
        steps {
            sh '''
            docker run --rm \
            -v $(pwd):/zap/wrk \
            owasp/zap2docker-stable \
            zap-baseline.py \
            -t http://host.docker.internal:5000 || true
            '''
        }
    }
}

post {
    always {
        sh 'docker rm -f $CONTAINER_NAME || true'
        cleanWs()
    }

    success {
        echo "PIPELINE SUCCESS"
    }

    failure {
        echo "PIPELINE FAILED"
    }
}
```

}

