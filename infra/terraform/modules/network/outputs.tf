output "vpc_id" {
  description = "VPC id."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "VPC CIDR block."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet ids."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet ids."
  value       = aws_subnet.private[*].id
}

output "nat_gateway_id" {
  description = "NAT gateway id (null if disabled)."
  value       = try(aws_nat_gateway.this[0].id, null)
}

output "public_route_table_id" {
  description = "Public route table id."
  value       = aws_route_table.public.id
}

output "private_route_table_id" {
  description = "Private route table id."
  value       = aws_route_table.private.id
}
