from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.components.routers import parse, to_tex, qa_generate, quality, qa_dedup
from app.components.core.database import init_db, get_database
app = FastAPI(title="LLM-Kit API")

# 添加基本的CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



async def clear_all_collections():
    """清空所有集合的数据"""
    db = await get_database()
    collections = [
        "parse_records",
        "tex_records",
        "qa_generations",
        "qa_pairs",
        "quality_generations",
        "quality_records",
        "dedup_records",
        "kept_pairs"
    ]
    for collection_name in collections:
        collection = db.llm_kit[collection_name]  # 获取正确的集合引用
        try:
            await collection.delete_many({})  # 使用异步删除方法
            print(f"Cleared collection: {collection_name}")
        except Exception as e:
            print(f"Error clearing collection {collection_name}: {str(e)}")

# 注册路由
app.include_router(parse.router, prefix="/parse", tags=["parse"])
app.include_router(to_tex.router, prefix="/to_tex", tags=["to_tex"])
app.include_router(qa_generate.router, prefix="/qa", tags=["qa_generate"])
app.include_router(quality.router, prefix="/quality", tags=["quality"])
app.include_router(qa_dedup.router, prefix="/dedup", tags=["qa_dedup"])

# 健康检查接口
@app.get("/")
async def root():
    return {"status": "ok", "message": "LLM-Kit API is running"}

@app.post("/clear-data")
async def clear_data():
    """手动清空所有数据的API端点"""
    await clear_all_collections()
    return {"message": "All collections cleared successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
"""
import os

from deduplication.qa_deduplication import QADeduplication
from generate_qas.qa_generator import QAGenerator
from quality_control.quality_control import QAQualityGenerator
from text_parse.parse import parse
from text_parse.to_tex import LatexConverter
from utils.hparams import DedupParams, HyperParams

def dedup():
    hparams=DedupParams.from_dedup_yaml('hparams/dedup.yaml')
    qa_dedup=QADeduplication(hparams)
    qa_dedup.process_qa_file(hparams)

def main():
    hparams=HyperParams.from_hparams('hyparams/config.yaml')

    file_list=[]  #待处理文件列表
    if os.path.isdir(hparams.file_path):
        files=os.listdir(hparams.file_path)
        for file in files:
            file_list.append(file)
    elif os.path.isfile(hparams.file_path):
        file_list.append(hparams.file_path)


    for file in file_list:
        print('Start iterative optimization of ' + os.path.basename(file))
        parsed_file_path=parse(hparams)  #对原始材料进行解析，返回解析后文本数据
        latex_converter=LatexConverter(parsed_file_path, hparams)
        if file.split('.')[-1]!='tex' and hparams.convert_to_tex==True:
            latex_converter.convert_to_latex()
        elif file.split('.')[-1]=='tex':
            pass
            # 仍然
        
        qa_generator=QAGenerator(latex_converter.save_path, hparams)
        qa_path=qa_generator.convert_tex_to_qas()

        # 质量控制
        quality_control=QAQualityGenerator(qa_path, hparams)
        it_path=quality_control.iterate_optim_qa()
        
        

            

if __name__=='__main__':
    main()

        
        
        
    

            
                
    
 
        
    

"""

