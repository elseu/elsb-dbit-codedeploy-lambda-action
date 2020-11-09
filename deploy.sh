#!/bin/sh

export APP_NAME=$INPUT_APP_NAME
export DEPLOYMENT_GROUP=$INPUT_DEPLOYMENT_GROUP
export PACKAGE_S3_BUCKET=$INPUT_PACKAGE_S3_BUCKET
export PACKAGE_S3_KEY=$INPUT_PACKAGE_S3_KEY
export FUNCTION_NAME=$INPUT_FUNCTION_NAME
export ALIAS=$INPUT_ALIAS

echo "Getting the current version of the function"
CURRENT_FUNCTION_VERSION=$(aws lambda get-function-configuration --function-name $FUNCTION_NAME | jq '.Version')
echo "Updating the function code"
aws lambda update-function-code --function-name $FUNCTION_NAME --s3-bucket $PACKAGE_S3_BUCKET --s3-key $PACKAGE_S3_KEY
echo "Publishing a new version of the function and getting the new version id"
NEW_FUNCTION_VERSION=$(aws lambda publish-version --function-name $FUNCTION_NAME | jq '.Version')

echo "Create AppSpec.json"
FILE_CONTENT="{'version': '0.0',
'Resources': [{
  '${FUNCTION_NAME}': {
    'Type': 'AWS::Lambda::Function',
    'Properties': {
      'Name': '${FUNCTION_NAME}',
      'Alias': '${ALIAS}',
      'CurrentVersion': ${CURRENT_FUNCTION_VERSION},
      'TargetVersion': ${NEW_FUNCTION_VERSION}
    }
  }
}],
'Hooks': []
}"
echo $FILE_CONTENT | sed "s/'/\"/g" > AppSpec.json
cat AppSpec.json

TIMESTAMP=$(date +'%Y%m%d-%H%M%S')
SPEC_FILENAME=${PACKAGE_S3_KEY}_${TIMESTAMP}_AppSpec.yaml
aws s3 cp AppSpec.json s3://${PACKAGE_S3_BUCKET}/${SPEC_FILENAME}

deployId=$(aws deploy create-deployment --application-name $APP_NAME --deployment-group-name $DEPLOYMENT_GROUP \
    --s3-location bucket=${PACKAGE_S3_BUCKET},key=${SPEC_FILENAME},bundleType=yaml \
    --output text --query deploymentId)
echo "Deployment ID: $deployId"
aws deploy wait deployment-successful --deployment-id $deployId