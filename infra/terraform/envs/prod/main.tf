module "jenie_prod"{
    source = "../../modules/jenie-platform"
    environment = "prod"
    vpc_cidr = "10.20.0.0/16"
    db_instance_class = "db.t4g.large"
    multi_az = true
    backup_retention_days = 30
    min_capacity = 2
    max_capacity = 10
}