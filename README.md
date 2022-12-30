

对于电商行业客户来说，在每年双十一/黑五等大促活动前夕平台都需要进行大量的资源扩容以应对即将到来的业务高峰。以EC2实例资源为例，一般来说需要客户提前对容量进行规划并通过AWS 相关流程来预留实例，从而确保该可用区内实例容量充足。由于整个流程需要数周甚至数月时间，因此该流程更适用于中长期规划的资源需求，而无法满足客户临时需求。针对此场景，可以考虑使用EventBridge+Lambda+Aurora的方式来自动化的对特定实例资源进行预留


# 服务介绍

## AWS Lambda

一项无服务器事件驱动型计算服务，该服务使您可以运行几乎任何类型的应用程序或后端服务的代码，而无需预置或管理服务器。Lambda 在可用性高的计算基础设施上运行您的代码，执行计算资源的所有管理工作，其中包括服务器和操作系统维护、容量调配和弹性伸缩和记录。您可以从 200 多个 AWS 服务和软件即服务 (SaaS) 应用程序中触发 Lambda，且只需按您的使用量付费。  
https://aws.amazon.com/cn/lambda/ 

## Amazon Aurora Serverless

Amazon Aurora 的一种按需自动扩展配置版本。Amazon Aurora Serverless 会根据应用程序的需求自动启动、关闭以及扩展或缩减容量。 您可以在 AWS 上运行数据库，而无需管理数据库容量。手动管理数据库容量需要占用宝贵的时间，也可能导致数据库资源的使用效率低下。 借助 Aurora Serverless，您可以创建数据库，指定所需的数据库容量范围，然后连接您的应用程序。您需要在数据库处于活动状态期间按照每秒使用的数据库容量进行付费，并且只需在 Amazon Relational Database Service（Amazon RDS）控制台中执行几个步骤即可在标准配置和无服务器配置之间进行迁移。  
https://aws.amazon.com/cn/rds/aurora/serverless/?nc1=h_ls

## AWS ODCR

On-Demand Capacity Reservations,通过使用按需容量预留，您可以在特定可用区中为Amazon EC2实例预留计算容量达任意持续时间。通过创建容量预留，可以确保您始终能够在需要时访问 EC2 容量。您随时可以创建容量预留，而无需作出一年或三年期限承诺。在您的账户中预置容量预留后，容量即可用且账单开始。当您不再需要它时，请取消容量预留以释放容量并停止产生费用。  
https://docs.aws.amazon.com/zh_cn/AWSEC2/latest/UserGuide/ec2-capacity-reservations.html  
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.create_capacity_reservation  

## Amazon EventBridge

一种无服务器事件总线服务，让您可以轻松地将应用程序与来自各种源的数据相连接。 EventBridge 可以从应用程序、SaaS（Sa）应用程序和服务传输实时数据流，然后AWS将实时数据流传输到诸如AWS Lambda之类的目标、使用 API 目标的 HTTP 调用端点或其他AWS账户中的事件总线  
https://aws.amazon.com/cn/eventbridge/  
https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html  

## AWS Secrets Manager

Secrets Manager 允许您将代码中的硬编码凭证（包括密码）替换为对 Secrets Manager 的 API 调用，以便以编程方式检索密钥。这有助于确保密钥不会被检查代码的人员泄露，因为密钥不再位于代码中。此外，您还可以配置 Secrets Manager 以根据指定的计划自动轮换密钥。这样，您就可以将长期密钥替换为短期密钥，从而显著降低泄露风险  
https://aws.amazon.com/cn/secrets-manager/


# 整体架构
![image](https://github.com/percy-han/AWS-ODCR/blob/main/IMG/architect.png)
 

## 架构说明

Aurora数据库的表中存储了预留实例资源的相关信息，如实例类型，可用区，总需求数量和当前已预留数量。EventBridge定时触发Lambda来运行Python脚本，脚本先读取数据库中数据以判断哪些实例需要预留，随后调用ODCR API来预留实例。为了提高安全性，数据库的登陆信息均存储在Secrets Manager中，Lambda调用Secrets Manager来获取数据库登陆信息。

## 网络配置

Aurora和Lambda在同一个VPC内的不同的subnet中，也可部署在多个subnet上以提高可用性。另外，Lambda需要访问Aurora，并能通过互联网访问AWS服务（也可通过VPC Endpoint实现内网访问AWS服务）  

Subnet Name  | Subnet Type  | CIDR  | Application
 ---- | ----- | ------ | ------  
 Public_Subnet  | Public | 172.18.1.0/24 | NAT Gateway 
 Private_Subnet_DB_1  | Private | 172.18.2.0/24 | Aurora
 Private_Subnet_DB_2  | Private | 172.18.3.0/24 | Aurora
 Private_Subnet_Lambda_1  | Private | 172.18.4.0/24 | Lambda
 Private_Subnet_Lambda_2  | Private | 172.18.5.0/24 | Lambda


# 使用说明
## 数据库初始化

整体方案部署完毕后，第一步需要对数据库进行初始化操作：创建表，插入数据，更改数据等常规CRUD操作。可使用Query Editor登陆到数据库以执行SQL(Lambda脚本中Initial_db_sql()函数也可进行相关SQL操作)
![image](https://github.com/percy-han/AWS-ODCR/blob/main/IMG/query-editor.png)
### 创建数据库
#创建Aurora时已经自动执行，不需要额外操作  
`CREATE DATABASE IF NOT EXISTS <database> DEFAULT CHARACTER SET utf8`
### 创建资源需求元数据表
#创建资源预留表，为保证数据唯一性，这里对InstanceType和AvailabilityZone列做了复合主键  
`CREATE Table IF NOT EXISTS <database>.odcr_capacity  
(InstanceType varchar(255),  
AvailabilityZone varchar(255),PRIMARY KEY (InstanceType,AvailabilityZone),  
Target_Capacity int NOT NULL,  
Current_Capacity int DEFAULT 0)`   
### 插入数据
#根据具体的资源需求，在表中插入对应数据，当Target_Capacity> Current_Capacity时脚本会调用资源预留API。如：需要在ap-northeast-1c可用区预留15台r5b.2xlarge实例，则可执行以下SQL  
`INSERT INTO <database>.odcr_capacity VALUES ('r5b.2xlarge','ap-northeast-1c',15,0)`  
### 更新数据
#根据资源需求变化更新相关数据  
`update <database>.odcr_capacity set Current_Capacity=5 where InstanceType='r5b.2xlarge' and AvailabilityZone='ap-northeast-1a'`  
### 查询所有数据
`SELECT * FROM <database>.odcr_capacity`  

## 检查执行结果

可在Lambda控制台的Monitor中查看相关执行log并在EC2控制台查看预留的资源
![image](https://github.com/percy-han/AWS-ODCR/blob/main/IMG/lambda-monitor.png)
![image](https://github.com/percy-han/AWS-ODCR/blob/main/IMG/odcr1.png)
 
## 启动实例

代码示例中创建的open模式的ODCR，因此在启动实例时只需要确保在对应可用区启动该实例类型的EC2即可，ODCR会被自动应用。
![image](https://github.com/percy-han/AWS-ODCR/blob/main/IMG/odcr2.png)
https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-reservations-using.html#capacity-reservations-launch 
注意：当使用ODCR实现了实例预留并且EC2实例成功启动后，即便实例终止也依然会对该ODCR收费，因此需要客户评估实例启动之后ODCR是否取消。


# 方案配置

该方案配置主要以AWS CLI方式来实现，要求CLI版本为2.0以上

## 创建网络
### 检查AWS CLI版本
`~$ aws --version`
### 创建VPC
`~$ export AWS_Region=<region_name>`  
`~$ export AWS_AZ_a=<az-a>`  
`~$ export AWS_AZ_c=<az-c>`  
`~$ export VPC_ID=$(aws ec2 create-vpc --cidr-block 172.18.0.0/16 --instance-tenancy default  --tag-specifications ResourceType=vpc,Tags='[{Key=Project,Value=ODCR}]' --region $AWS_Region --output text --query Vpc.[VpcId][0])`
### 创建公有子网
`~$ export Public_Subnet_ID=$(aws ec2 create-subnet --tag-specifications ResourceType=subnet,Tags='[{Key=Project,Value=ODCR}]' --availability-zone $AWS_AZ_a --cidr-block 172.18.1.0/24 --vpc-id $VPC_ID --region $AWS_Region --output text --query Subnet.[SubnetId][0])`
### 分配EIP并创建NAT Gateway
`~$ export Allocation_ID=$(aws ec2 allocate-address --tag-specifications ResourceType=elastic-ip,Tags='[{Key=Project,Value=ODCR}]' --region $AWS_Region --output text --query AllocationId)`  
`~$ export NatGW_ID=$(aws ec2 create-nat-gateway --subnet-id $Public_Subnet_ID --tag-specifications ResourceType=natgateway,Tags='[{Key=Project,Value=ODCR}]' --connectivity-type public --allocation-id $Allocation_ID --region $AWS_Region --output text --query NatGateway.[NatGatewayId][0])`
### 创建Internet GateWay并附加到该VPC 
`~$ export IGW_ID=$(aws ec2 create-internet-gateway --tag-specifications ResourceType=internet-gateway,Tags='[{Key=Project,Value=ODCR}]' --region $AWS_Region --output text --query InternetGateway.[InternetGatewayId][0])`  
`~$ aws ec2 attach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID --region $AWS_Region`
### 创建私有子网
`~$ export Private_Subnet_DB_1=$(aws ec2 create-subnet --tag-specifications ResourceType=subnet,Tags='[{Key=Project,Value=ODCR}]' --availability-zone $AWS_AZ_a --cidr-block 172.18.2.0/24 --vpc-id $VPC_ID --region $AWS_Region --output text --query Subnet.[SubnetId][0])`  
`~$ export Private_Subnet_DB_2=$(aws ec2 create-subnet --tag-specifications ResourceType=subnet,Tags='[{Key=Project,Value=ODCR}]' --availability-zone $AWS_AZ_c --cidr-block 172.18.3.0/24 --vpc-id $VPC_ID --region $AWS_Region --output text --query Subnet.[SubnetId][0])`  
`~$ export Private_Subnet_Lambda_1=$(aws ec2 create-subnet --tag-specifications ResourceType=subnet,Tags='[{Key=Project,Value=ODCR}]' --availability-zone $AWS_AZ_a --cidr-block 172.18.4.0/24 --vpc-id $VPC_ID --region $AWS_Region --output text --query Subnet.[SubnetId][0])`  
`~$ export Private_Subnet_Lambda_2=$(aws ec2 create-subnet --tag-specifications ResourceType=subnet,Tags='[{Key=Project,Value=ODCR}]' --availability-zone $AWS_AZ_c --cidr-block 172.18.5.0/24 --vpc-id $VPC_ID --region $AWS_Region --output text --query Subnet.[SubnetId][0])`  
### 配置主路由
#关联公有子网并添加默认路由到IGW  
`~$ export Main_Route_Table_ID=$(aws ec2 describe-route-tables --filters Name=vpc-id,Values=$VPC_ID --region $AWS_Region --output text --query RouteTables[0].[RouteTableId][0])`  
`~$ aws ec2 associate-route-table --route-table-id $Main_Route_Table_ID --subnet-id $Public_Subnet_ID --region $AWS_Region`  
`~$ aws ec2 create-route --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID --route-table-id $Main_Route_Table_ID --region $AWS_Region`
### 配置私有路由
#创建私有路由表  
`~$ export Private_Route_Table_ID=$(aws ec2 create-route-table --vpc-id $VPC_ID --tag-specifications ResourceType=route-table,Tags='[{Key=Project,Value=ODCR}]' --region $AWS_Region --output text --query RouteTable.[RouteTableId])`  
#关联私有子网  
`~$ aws ec2 associate-route-table --route-table-id $Private_Route_Table_ID --subnet-id $Private_Subnet_DB_1 --region $AWS_Region`  
`~$ aws ec2 associate-route-table --route-table-id $Private_Route_Table_ID --subnet-id $Private_Subnet_DB_2 --region $AWS_Region`  
`~$ aws ec2 associate-route-table --route-table-id $Private_Route_Table_ID --subnet-id $Private_Subnet_Lambda_1 --region $AWS_Region`  
`~$ aws ec2 associate-route-table --route-table-id $Private_Route_Table_ID --subnet-id $Private_Subnet_Lambda_2 --region $AWS_Region`  
#添加默认路由到NAT GW  
`~$ aws ec2 create-route --destination-cidr-block 0.0.0.0/0 --gateway-id $NatGW_ID --route-table-id $Private_Route_Table_ID --region $AWS_Region`  
### 创建Security Group
#创建Lambda SG，inbound rules保持为空，outbound rules可以放开所有  
`~$ export ODCR_Lambda_SG_Name=<odcr-lambda-sg>`  
`~$ export ODCR_Lambda_SG_ID=$(aws ec2 create-security-group --description "odcr-lambda-sg" --group-name $ODCR_Lambda_SG_Name --vpc-id $VPC_ID --tag-specifications ResourceType=security-group,Tags='[{Key=Project,Value=ODCR}]' --region $AWS_Region --output text --query GroupId)`  
#创建Aurora security group，inbound rules配置为允许上一步的Lambda的SG访问3306端口  
`~$ export ODCR_RDS_SG_Name=<odcr-rds-sg>`  
`~$ export ODCR_RDS_SG_ID=$(aws ec2 create-security-group --description "odcr-rds-sg" --group-name $ODCR_RDS_SG_Name --vpc-id $VPC_ID --tag-specifications ResourceType=security-group,Tags='[{Key=Project,Value=ODCR}]' --region $AWS_Region --output text --query GroupId)`  
`~$ aws ec2 authorize-security-group-ingress --group-id $ODCR_RDS_SG_ID --protocol tcp --port 3306 --source-group $ODCR_Lambda_SG_ID --tag-specifications  ResourceType=security-group-rule,Tags='[{Key=Project,Value=ODCR}]'  --region $AWS_Region`  

 ## 创建Aurora 

### 创建Subnet Groups  
`~$ export ODCR_RDS_Subnet_Group_Name=<odcr-rds-subnet-group>`  
`~$ aws rds create-db-subnet-group --db-subnet-group-name $ODCR_RDS_Subnet_Group_Name --db-subnet-group-description "ODCR RDS Subnet Group"  --subnet-ids $Private_Subnet_DB_1 $Private_Subnet_DB_2  --tags Key=Project,Value=ODCR --region $AWS_Region`  
### 创建Aurora Serverless 
`~$ export rds_username=<db_username>`  
`~$ export rds_password=<db_password>`  
`~$ export rds_db_cluster_identifier=<db_identifier>`  
`~$ export rds_endpoint=$(aws rds create-db-cluster --database-name odcr_db --db-cluster-identifier $rds_db_cluster_identifier --vpc-security-group-ids $ODCR_RDS_SG_ID --db-subnet-group-name $ODCR_RDS_Subnet_Group_Name --engine aurora --port 3306 --master-username $rds_username --master-user-password $rds_password  --engine-mode serverless --scaling-configuration MinCapacity=1,MaxCapacity=4,AutoPause=false,TimeoutAction=ForceApplyCapacityChange  --enable-http-endpoint --tags Key=Project,Value=ODCR --output text --query DBCluster.[Endpoint][0] --region $AWS_Region)`  
## 创建Secret Manager

`~$ export secret_manager_rds_name=<secret-manager-name>`  
`~$ aws secretsmanager create-secret --name $secret_manager_rds_name --description "Credentials for serverless DB" --secret-string "{\"username\":\"${rds_username}\",\"password\":\"${rds_password}\",\"host\":\"${rds_endpoint}\",\"port\":3306,\"dbname\":\"odcr_db\"}" --tags Key=Project,Value=ODCR --region $AWS_Region`  

 ## 创建Lambda

### 创建IAM Policy
~$ cat odcr-iam-policy.json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "ec2:CreateNetworkInterface",
                "ec2:DeleteNetworkInterface",
                "ec2:Describe*"
            ],
            "Resource": "*"
        },
        {
            "Sid": "VisualEditor1",
            "Effect": "Allow",
            "Action": [
                "ec2:ModifyCapacityReservation",
                "ec2:CreateCapacityReservation",
                "ec2:CancelCapacityReservation"
            ],
            "Resource": "arn:aws:ec2:*:*:capacity-reservation/*"
        },
        {
            "Sid": "VisualEditor2",
            "Effect": "Allow",
            "Action": "ec2:CreateTags",
            "Resource": "arn:aws:ec2:*:*:capacity-reservation/*"
        },
        {
            "Sid": "VisualEditor3",
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetRandomPassword",
                "secretsmanager:GetResourcePolicy",
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret",
                "secretsmanager:ListSecretVersionIds",
                "secretsmanager:ListSecrets"
            ],
            "Resource": "*"
        }
    ]
}  
#<your-path>为odcr-iam-policy.json文件本地路径  
`~$ export odcr_iam_policy_name=<iam-policy-name>`  
`~$ export odcr_policy_arn=$(aws iam create-policy --policy-name $odcr_iam_policy_name --policy-document file://<your-path>/odcr-iam-policy.json --tags Key=Project,Value=ODCR --region $AWS_Region --output text --query Policy.[Arn][0])`  
### 创建IAM Role并附加策略
~$ cat iam-assume-role.json  
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}  
#<your-path>为iam-assume-role.json文件本地路径  
`~$ export odcr_role_name=<iam-role-name>`  
`~$ export odcr_role_arn=$(aws iam create-role --role-name $odcr_role_name --assume-role-policy-document file://<your-path>/iam-assume-role.json --tags Key=Project,Value=ODCR --region $AWS_Region --output text --query Role.[Arn][0])`  
#附加自定义策略和托管策略  
`~$ aws iam attach-role-policy --policy-arn $odcr_policy_arn --role-name $odcr_role_name --region $AWS_Region`  
`~$ aws iam attach-role-policy --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole --role-name $odcr_role_name --region $AWS_Region`  
`~$ aws iam attach-role-policy --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole --role-name $odcr_role_name --region $AWS_Region`  
### 创建Lambda Function
下载Lambda deployment package odcr-deployment-package.zip到本地 
#<your-path>为odcr-deployment-package.zip文件本地路径  
`~$ export odcr_lambda_name=<lambda-name>`  
`~$ export odcr_lambda_arn=$(aws lambda create-function \  
    --function-name $odcr_lambda_name \  
    --runtime python3.9 \  
    --architectures x86_64 \  
    --package-type Zip \  
    --zip-file fileb://<your-path>/odcr-deployment-package.zip \  
    --handler odcr_lambda.lambda_handler \  
    --timeout 300 \  
    --vpc-config SubnetIds=$Private_Subnet_Lambda_1,$Private_Subnet_Lambda_2,SecurityGroupIds=$ODCR_Lambda_SG_ID \  
    --environment "Variables={RegionName=$AWS_Region,SecretName=$secret_manager_rds_name}" \  
    --role $odcr_role_arn \  
    --tags Key=Project,Value=ODCR \  
    --region $AWS_Region \  
    --output text \  
    --query FunctionArn)`  
### 添加触发器
#创建event bridge，其中：schedule-expression 'rate(5 minutes)  表示每5分钟执行一次  
`~$ export event_bridge_arn=$(aws events put-rule --name my-scheduled-rule --schedule-expression 'rate(5 minutes)' --tags Key=Project,Value=ODCR --region $AWS_Region --output text --query RuleArn)`  
`~$ aws lambda add-permission --function-name $odcr_lambda_name --statement-id my-scheduled-event --action 'lambda:InvokeFunction' --principal events.amazonaws.com --source-arn $event_bridge_arn --region $AWS_Region`  
`~$ aws events put-targets --rule my-scheduled-rule --targets "Id"="1","Arn"=$odcr_lambda_arn --region $AWS_Region`  

# 结论
通过EventBridge+Lambda+Aurora可以实现自动化对EC2实例进行资源预留，从而满足客户短期内的资源需求。同时采用serverless服务也可以最大程度上减少维护成本并实现成本节约。
