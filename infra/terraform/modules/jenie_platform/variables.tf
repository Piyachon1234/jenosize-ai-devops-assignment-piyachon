variable "environment" {type = string}
variable "aws_region" {type = string, default= "ap-southeast-1"}
variable "vpc_cidr"{type=string}
variable "container_image" {type=string}
variable "db_instance_class"{type=string}
variable "multi_az" {type=bool}
variable "backup_retention_days {type=number}
variable "min_capacity" {type=number}
variable "max_capacity"{type=number}