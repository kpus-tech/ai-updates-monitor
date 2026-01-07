"""CDK Stack for AI Updates Monitor infrastructure."""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnParameter,
    CfnOutput,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct
import os


class AiUpdatesStack(Stack):
    """Stack containing all AI Updates Monitor resources."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =====================
        # Parameters
        # =====================
        email_param = CfnParameter(
            self,
            "NotificationEmail",
            type="String",
            description="Email address to receive AI/ML update notifications",
            allowed_pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$",
            constraint_description="Must be a valid email address",
        )

        # =====================
        # DynamoDB Table
        # =====================
        state_table = dynamodb.Table(
            self,
            "StateTable",
            table_name="ai_updates_state",
            partition_key=dynamodb.Attribute(
                name="source_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=False,
        )

        # =====================
        # SNS Topic
        # =====================
        notification_topic = sns.Topic(
            self,
            "NotificationTopic",
            topic_name="ai-updates-notifications",
            display_name="AI/ML Updates",
        )

        # Email subscription
        notification_topic.add_subscription(
            subscriptions.EmailSubscription(email_param.value_as_string)
        )

        # =====================
        # Lambda Function
        # =====================
        lambda_path = os.path.join(os.path.dirname(__file__), "..", "..", "lambda")

        monitor_function = lambda_.Function(
            self,
            "MonitorFunction",
            function_name="ai-updates-monitor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                lambda_path,
                bundling={
                    "image": lambda_.Runtime.PYTHON_3_12.bundling_image,
                    "command": [
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                },
            ),
            timeout=Duration.seconds(120),
            memory_size=512,
            environment={
                "STATE_TABLE_NAME": state_table.table_name,
                "SNS_TOPIC_ARN": notification_topic.topic_arn,
                "LOG_LEVEL": "INFO",
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # Grant permissions
        state_table.grant_read_write_data(monitor_function)
        notification_topic.grant_publish(monitor_function)

        # =====================
        # EventBridge Schedule (every 2 hours)
        # =====================
        schedule_rule = events.Rule(
            self,
            "ScheduleRule",
            rule_name="ai-updates-schedule",
            description="Triggers AI Updates Monitor every 2 hours",
            schedule=events.Schedule.rate(Duration.hours(2)),
        )

        schedule_rule.add_target(
            targets.LambdaFunction(
                monitor_function,
                retry_attempts=2,
            )
        )

        # =====================
        # Outputs
        # =====================
        CfnOutput(
            self,
            "TableName",
            value=state_table.table_name,
            description="DynamoDB table name for state storage",
        )

        CfnOutput(
            self,
            "TopicArn",
            value=notification_topic.topic_arn,
            description="SNS topic ARN for notifications",
        )

        CfnOutput(
            self,
            "FunctionName",
            value=monitor_function.function_name,
            description="Lambda function name",
        )

        CfnOutput(
            self,
            "FunctionArn",
            value=monitor_function.function_arn,
            description="Lambda function ARN",
        )
