module "jenie_dev"{
    source = "../../modules/jenie-platform"
    environment = "dev"
    vpc_cidr = "10.10.0.0/16"
    db_instance_class = "db.t4g.micro"
    multi_az = false
    backup_retention_days = 7
    min_capacity = 1
    max_capacity = 2
}