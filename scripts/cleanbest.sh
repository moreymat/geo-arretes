#!/usr/bin/env bash
DATA_RAW=data/raw
DATA_INT=data/interim
DATA_PRO=data/processed
#
# DIR_IN=${DATA_RAW}/arretes_peril_hors_marseille_2018_2022
# BATCH=hors_marseille_2018_2022
#
# DIR_IN=${DATA_RAW}/arretes_peril_compil
# BATCH=arretes_peril_compil
#
DIR_IN=${DATA_RAW}/actes_2022_traites
BATCH=actes_2022_traites

# fichiers produits par parsebest.sh
rm ${DATA_INT}/${BATCH}_meta_ntxt_proc_struct.csv
rm ${DATA_INT}/${BATCH}_meta_ntxt_doc_struct.csv
rm ${DATA_INT}/${BATCH}_data_struct.csv
rm ${DATA_INT}/${BATCH}_data_enr_struct.csv 
rm -Rf ${DATA_PRO}/${BATCH}_struct
