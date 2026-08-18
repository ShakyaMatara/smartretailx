import boto3
from botocore.exceptions import ClientError

from config import settings


def dynamodb_resource():
    return boto3.resource(
        "dynamodb",
        endpoint_url=settings.aws_endpoint_url,
        region_name=settings.aws_default_region,
    )


def init_table():
    dynamodb = dynamodb_resource()
    try:
        dynamodb.meta.client.describe_table(TableName=settings.inventory_table)
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    dynamodb.create_table(
        TableName=settings.inventory_table,
        KeySchema=[{"AttributeName": "product_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "product_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    ).wait_until_exists()


def inventory_table():
    return dynamodb_resource().Table(settings.inventory_table)
