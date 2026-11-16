output "vpc_id" {value=aws_vpc.main.id}
output "ecs_cluster_name"{value = aws_ecs_cluster.main.name}
output "ecs_service_name"{value= aws_ecs_service.api.name}
output "secrets_manager_arn"{value=aws_secretsmanager_secret.app_secrets.arn}
output "rds_endpoint"{value=aws_db_instance.postgres.endpoint}