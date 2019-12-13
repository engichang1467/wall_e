#!/bin/bash


## TODO: MATCH THE FORMAT TO CREATE-DEV-DOCKER-IMAGE SO THAT IT WILL READ THE PREVIOUS COMMIT FROM A FILE RATHER THAN
## ASSUME IT WAS ONLY THE PREVIOUS COMMIT.
set -e -o xtrace
# https://stackoverflow.com/a/5750463/7734535

IMAGENAME="wall_e"
DOCKERREGISTRY="sfucsssorg"
DOCKERFILE="CI/server_scripts/Dockerfile.base"

export testContainerDBName="TEST_${BRANCH_NAME}_wall_e_db"
export testContainerName="TEST_${BRANCH_NAME}_wall_e"
export prodContainerName="PRODUCTION_${BRANCH_NAME}_wall_e"

BRANCH_NAME=$(echo "$BRANCH_NAME" | awk '{print tolower($0)}')

export prodImageName="production_${BRANCH_NAME}_wall_e"
export testImageName="test_${BRANCH_NAME}_wall_e"

re_create_image () {
    docker stop "${testContainerDBName}" "${testContainerName}" "${prodContainerName}" || true
    docker rm "${testContainerDBName}" "${testContainerName}" "${prodContainerName}" || true
    docker image rm -f "${prodImageName}" "${testImageName}" "${IMAGENAME}" "${DOCKERREGISTRY}/${IMAGENAME}" || true
    docker build --no-cache -t ${IMAGENAME} -f ${DOCKERFILE} --build-arg CONTAINER_HOME_DIR=${CONTAINER_HOME_DIR} .
    docker tag ${IMAGENAME} ${DOCKERREGISTRY}/${IMAGENAME}
    echo "${DOCKER_HUB_PASSWORD}" | docker login --username=${DOCKER_HUB_USER_NAME} --password-stdin
    docker push ${DOCKERREGISTRY}/${IMAGENAME}
    current_commit=$(git log -1 --pretty=format:"%H")
    mkdir -p "${JENKINS_HOME}"/wall_e_commits
    echo "${current_commit}" > "${JENKINS_HOME}"/wall_e_commits/"${COMPOSE_PROJECT_NAME}"
    exit 0
}

if [ ! -f "${JENKINS_HOME}"/wall_e_commits/"${COMPOSE_PROJECT_NAME}" ]; then
    echo "No previous commits detected. Will [re-]create ${testBaseImageName_lowerCase} docker image"
    re_create_image
else
    echo "previus commit detected. Will now test to se if re-creation is needed"
    current_commit=$(git log -1 --pretty=format:"%H")
    previous_commit=$(cat "${JENKINS_HOME}"/wall_e_commits/"${COMPOSE_PROJECT_NAME}")
    files_changed=($(git diff --name-only "${current_commit}" "${previous_commit}"))
    for file_changed in "${files_changed[@]}"
    do
        if [[ "${file_changed}" == "wall_e/src/requirements.txt" || "${file_changed}" == "${DOCKERFILE}" ]]; then
            echo "will need to re-create docker image ${testBaseImageName_lowerCase}"
            re_create_image
        fi
    done
fi

echo "No modifications were needed to base image"
echo "${current_commit}" > "${JENKINS_HOME}"/wall_e_commits/"${COMPOSE_PROJECT_NAME}"
exit 0
