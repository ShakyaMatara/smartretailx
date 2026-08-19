import boto3
from botocore.exceptions import ClientError

from config import settings


def dynamodb_resource():
    """DynamoDB client.

    endpoint_url is only passed when explicitly configured. Against real
    AWS it is omitted entirely and boto3 resolves the regional endpoint,
    so the identical image runs locally against LocalStack and in AWS
    against the managed service.
    """
    kwargs = {"region_name": settings.aws_default_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.resource("dynamodb", **kwargs)


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
