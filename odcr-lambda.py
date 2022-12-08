import boto3
import json
import pymysql
import os
import sys
from botocore.exceptions import ClientError


def get_secret(secretname, regionname):
    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager',
                            region_name=regionname)
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secretname)
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


class DBUtil():
    # Initiating
    def __init__(self, db_paras):
        self.conn = None
        self.cursor = None
        self.dbhost = db_paras['host']
        self.dbport = db_paras['port']
        self.dbuser = db_paras['username']
        self.dbpassword = db_paras['password']
        self.db = db_paras['dbname']

    # Create New Connection
    def get_conn(self):
        try:
            if self.conn is None:
                self.conn = pymysql.connect(host=self.dbhost,
                                            port=self.dbport,
                                            user=self.dbuser,
                                            password=self.dbpassword,
                                            database=self.db)
            return self.conn
        except Exception as e:
            sys.exit('Error: Cant connect Database')

    # Get Cursor
    def get_cursor(self):
        try:
            if self.cursor is None:
                self.cursor = self.get_conn().cursor()
            return self.cursor
        except Exception as e:
            sys.exit('Error: Cant get Cursor')

    # Execute SQL
    def exe_sql(self, sql):
        try:
            self.cursor = self.get_cursor()
            self.cursor.execute(sql)
            # If SQL is query
            if sql.split()[0].lower() == "select":
                return self.cursor.fetchall()
            # otherwise
            else:
                # commit transaction
                self.conn.commit()
                print('SQL commit success: ' + sql)
                return self.cursor.rowcount
        except Exception as e:
            # rollback transaction
            print('Error: Cant commit SQL: ' + sql)
            print(e)
            self.conn.rollback()

        finally:
            self.close_cursor()
            self.close_conn()

    # Close cursor
    def close_cursor(self):
        if self.cursor:
            self.cursor.close()
            self.cursor = None

    # Close Connection
    def close_conn(self):
        if self.conn:
            self.conn.close()
            self.conn = None


def Initial_db_sql(db_para):
    db_name = db_para['dbname']
    #Initial SQL for ODCR
    initate_db_sql = "CREATE DATABASE IF NOT EXISTS " + db_name + "DEFAULT CHARACTER SET utf8"

    initate_table_sql = "CREATE Table IF NOT EXISTS " + db_name + ".odcr_capacity (InstanceType varchar(255),AvailabilityZone varchar(255),PRIMARY KEY (InstanceType,AvailabilityZone),Target_Capacity int NOT NULL,Current_Capacity int DEFAULT 0)"

    insert_data_sql = "INSERT INTO " + db_name + ".odcr_capacity VALUES ('r5b.2xlarge','ap-northeast-1c',11,0)"

    update_table_sql = "update " + db_name + ".odcr_capacity set Current_Capacity=0 where InstanceType='r5b.4xlarge' and AvailabilityZone='ap-northeast-1a'"

    query_all_sql = "SELECT * FROM " + db_name + ".odcr_capacity"
    #execute SQL
    #DBUtil(db_para).exe_sql(initate_table_sql)
    #DBUtil(db_para).exe_sql(insert_data_sql)
    #DBUtil(db_para).exe_sql(update_table_sql)
    table_content = DBUtil(db_para).exe_sql(query_all_sql)
    print('Table Content: ')
    for row in table_content:
        print(row)


#Execute OD Reservation
def odcr_run(regionname, db_con_paras, instance_type, request_capacity,
             zone_name):
    try:
        print('Reserving:', instance_type, zone_name)
        client = boto3.client(service_name='ec2', region_name=regionname)
        odcr_response = client.create_capacity_reservation(
            InstanceType=instance_type,
            InstancePlatform='Linux/UNIX',
            AvailabilityZone=zone_name,
            Tenancy='default',
            InstanceCount=request_capacity,
            EbsOptimized=True,
            InstanceMatchCriteria='open')
        #Response is success
        if odcr_response['CapacityReservation']['State'] in [
                'active', 'expired', 'pending'
        ]:
            SQL = "UPDATE odcr_capacity SET Current_Capacity=Current_Capacity+" + str(
                request_capacity
            ) + " WHERE InstanceType='" + instance_type + "' and AvailabilityZone='" + zone_name + "'"
            DBUtil(db_con_paras).exe_sql(SQL)
            print('Reserve Successful!')
        else:
            print('Reserve Failed')
    except Exception as e:
        print(e)


def odcr_main(db_secret, region_name):
    step = 10
    #Query all db content
    sql = "SELECT * FROM odcr_capacity"
    table_content = DBUtil(db_secret).exe_sql(sql)
    for row in table_content:
        instance_type = row[0]
        az_name = row[1]
        target_capacity = row[2]
        current_capacity = row[3]
        if current_capacity >= target_capacity:
            print('Database Content:', row)
            print(
                'The Requirement of Capacity has been fulfilled,no need further action!'
            )
            continue
        else:
            #Need reservation
            print('Database Content:', row)
            #If request capacity is less than the step,request all the capacity needed
            if target_capacity - current_capacity <= step:
                request_capacity = target_capacity - current_capacity
                print('Request Capacity:', request_capacity)
                odcr_run(region_name, db_secret, instance_type,
                         request_capacity, az_name)
            else:
                #If target capacity is larger than request step,request the capacity at this step
                loop_count = (target_capacity - current_capacity) // step
                while loop_count:
                    print('Request Capacity:', step)
                    loop_count = loop_count - 1
                    odcr_run(region_name, db_secret, instance_type, step,
                             az_name)
                remaining_capacity = (target_capacity -
                                      current_capacity) % step
                #Request the remaining capacity
                if remaining_capacity != 0:
                    print('Remaining Capacity:', remaining_capacity)
                    odcr_run(region_name, db_secret, instance_type,
                             remaining_capacity, az_name)


def lambda_handler(event, context):
    aws_secret = os.environ['SecretName']
    aws_region = os.environ['RegionName']
    db_secret_paras = get_secret(aws_secret, aws_region)
    #Initial_db_sql(db_secret_paras)
    odcr_main(db_secret_paras, aws_region)
