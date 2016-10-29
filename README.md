# emrer

Emrer is a Python script that can manipulate (currently start/stop) an EMR cluster, given a configuration file as parameter. The configuration file is YAML, which makes it friendlier to humans. It contains all the infrastructure information needed to start the cluster (subnets, security groups, etc.) and paths to the scripts the cluster would run.

To start the cluster, one would run:
```
./emrer start emrer_demo/emrer_demo.yaml
```
(the emrer_demo will not work as-is, infrastructure details need to be filled in properly)

To stop it, assuming the cluster doesn't stop automatically once the job is done:
```
./emrer start emrer_demo/emrer_demo.yaml
```

The ```emrer_example.yaml``` file contains a commented configuration that serves as bad documentation.

Everything (configuration and scripts) can be stored in one place, which effectively means that an EMR cluster set up using Emrer can be versioned in Git or similar. Local scripts will be uploaded to S3 by emrer when it runs and the S3 link will be passed to the cluster for execution. 

One obvious use case is automating MapReduce jobs. Another use case could be self-service MapReduce clusters in bigger companies, where the tech department looking over AWS hands over a configuration file and the people that need to process data just have to fill in the scripts that the cluster will execute. Or the other way around, create the cluster in Dev using Emrer, then hand over the configuration for release in production after the infrastructure details have been tweaked.

The current status of the script is 'works-for-me'. It does what I need, although it has the potential to do more. It could be extended with a "resize" command, or allow some aspects of a running cluster to be modified.

In the ```emrer_demo``` directory there's a full configuration for a cluster that will basically do nothing. It will start, create a file in /tmp, then the cluster will destroy itself. Of course, some details like subnets need to be changed. ```emrer_demo\emrer_demo.awscli``` contains the equivalent aws-cli command for starting the same cluster, after scripts have been manually uploaded to S3. It's more verbose and somewhat harder to read, in my opinion.
