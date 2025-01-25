# LLM Kit API 文档

## 目录
1. [文件解析接口](#文件解析接口)
2. [LaTeX转换接口](#latex转换接口) 
3. [问答生成接口](#问答生成接口)
4. [质量控制接口](#质量控制接口)
5. [去重接口](#去重接口)

## 文件解析接口

### 上传文本文件
```http
POST /upload
```

**请求参数:**
```json
{
  "filename": "test",  // 文件名(不含扩展名)
  "content": "this is a test file",   // 文件内容
  "file_type": "txt" // 文件类型: tex, txt, json, pdf
}
```

**响应:**
```json
{
  "status": "success",
  "message": "File uploaded successfully",
  "data": {
    "file_id": "string"
  }
}
```

### 上传二进制文件
```http
POST /upload/binary
```

**请求参数:**
- `file`: 二进制文件 (multipart/form-data)
- 支持的文件类型: pdf, jpg, jpeg, png

**响应:**
```json
{
  "status": "success",
  "message": "Binary file uploaded successfully",
  "data": {
    "file_id": "string",
    "filename": "string",
    "file_type": "string",
    "mime_type": "string",
    "size": "number",
    "status": "string"
  }
}
```

### 获取所有文件列表
```http
GET /files/all
```

**响应:**
```json
{
  "status": "success",
  "message": "All files retrieved successfully",
  "data": [
    {
      "filename": "string",
      "file_type": "string",
      "size": "number",
      "status": "string",
      "created_at": "datetime",
      "type": "text|binary",
      "mime_type": "string"  // 仅二进制文件
    }
  ]
}
```

### 获取最近上传的文本文件
```http
GET /upload/latest
```

**响应:**
```json
{
  "status": "success",
  "message": "Latest file retrieved successfully",
  "data": {
    "file_id": "string",
    "filename": "string",
    "content": "string",
    "file_type": "string",
    "size": "number",
    "status": "string",
    "created_at": "datetime"
  }
}
```

### 获取最近上传的二进制文件信息
```http
GET /upload/binary/latest
```

**响应:**
```json
{
  "status": "success",
  "message": "Latest binary file info retrieved successfully",
  "data": {
    "file_id": "string",
    "filename": "string",
    "file_type": "string",
    "mime_type": "string",
    "size": "number",
    "status": "string",
    "created_at": "datetime"
  }
}
```

### 获取二进制文件内容
```http
GET /upload/binary/{file_id}/content
```

**响应:**
- 返回二进制文件流
- Content-Type: 对应文件的MIME类型
- Content-Disposition: attachment; filename="原始文件名"

### 解析文件
```http
POST /parse
```

**请求参数:**
```json
{
  "save_path": "result/",  //所有结果的父文件夹
  "SK": ["string"],
  "AK": ["string"],
  "parallel_num": 1
}
```

**响应:**
```json
{
  "status": "success",
  "message": "File parsed successfully",
  "data": {
    "record_id": "string",
    "content": "string",
    "parsed_file_path": "string"
  }
}
```

### OCR识别
```http
POST /ocr
```

**请求参数:**
```json
{
  "file_path": "string",
  "save_path": "string"
}
```

**响应:**
```json
{
  "status": "success",
  "message": "OCR completed successfully",
  "data": {
    "record_id": "string",
    "result": "string",
    "save_path": "string"
  }
}
```

### 获取解析历史记录
```http
GET /parse/history
```

**响应:**
```json
{
  "status": "success",
  "message": "Records retrieved successfully",
  "data": {
    "records": [
      {
        "record_id": "string",
        "input_file": "string",
        "status": "string",
        "file_type": "string",
        "save_path": "string",
        "task_type": "string",
        "progress": "number",
        "created_at": "datetime"
      }
    ]
  }
}
```

### 获取任务进度
```http
GET /task/progress/{record_id}
```

**响应:**
```json
{
  "status": "success",
  "message": "Progress retrieved successfully",
  "data": {
    "progress": "number",
    "status": "string",
    "task_type": "string"
  }
}
```

## LaTeX转换接口

### 转换为LaTeX
```http
POST /to_tex
```

**请求参数:**
```json
{
  "content": "this is test text",
  "filename": "from parsed file list, not specified manually",
  "model_name": "erine",
  "save_path": "result/",
  "SK": ["fsffsss"],
  "AK": ["fsdfdsf"],
  "parallel_num": 1
}
```

**响应:**
```json
{
  "status": "success",
  "message": "内容已成功转换为LaTeX格式",
  "data": {
    "content": "string",
    "save_path": "string"
  }
}
```

### 获取已解析文件列表
```http
GET /parsed_files
```

**响应:**
```json
{
  "status": "success",
  "message": "已解析文件列表获取成功",
  "data": {
    "files": [
      {
        "filename": "string",
        "created_at": "datetime",
        "file_type": "string"
      }
    ]
  }
}
```

###  获取文件内容

![image-20250125224844875](D:\Code\Python\LLM-Kit\api.assets\image-20250125224844875.png)

## 问答生成接口

### 1. 生成问答对
```http
POST /generate_qa
```

**请求参数:**
```json
{
  "content": "['id':.....,]",          // 输入文本内容,json content, from get content interface
  "filename": "string",         // 文件名.from parsed file list, not specified manually
  "model_name": "erine",       // 使用的模型名称
  "domain": "medical",          // 领域
  "save_path": "result/",       // 保存路径
  "SK": ["string"],           // Secret Key列表
  "AK": ["string"],           // Access Key列表
  "parallel_num": 1    // 并行处理数量
}
```

**响应:**
```json
{
  "status": "success",
  "message": "QA pairs generated successfully",
  "data": {
    "qa_pairs": [
      {
        "question": "string",
        "answer": "string"
      }
    ],
    "save_path": "string"      // 结果保存路径
  }
}
```

### 2. 获取TEX文件列表
```http
GET /tex_files
```

**响应:**
```json
{
  "status": "success",
  "message": "获取文件列表成功",
  "data": {
    "files": [
      {
        "filename": "string",
        "created_at": "datetime",
        "file_type": "string",
        "size": "number",
        "status": "string"
      }
    ]
  }
}
```

### 3. 获取TEX文件内容
```http
GET /tex_content/{filename}
```

**参数说明:**
- `filename`: TEX文件名

**响应:**
```json
{
  "status": "success",
  "message": "获取文件内容成功",
  "data": {
    "content": "string",
    "filename": "string",
    "created_at": "datetime",
    "file_type": "string"
  }
}
```

### 4. 获取生成历史记录
```http
GET /generate_qa/history
```

**响应:**
```json
{
  "status": "success",
  "message": "Records retrieved successfully",
  "data": {
    "records": [
      {
        "input_file": "string",
        "save_path": "string",
        "model_name": "string",
        "domain": "string",
        "status": "string",
        "progress": "number",
        "created_at": "datetime",
        "qa_pairs_count": "number"
      }
    ]
  }
}
```

### 状态说明

#### 任务状态(status)
- `processing`: 问答对生成中
- `completed`: 生成完成
- `failed`: 生成失败

#### 进度说明(progress)
- 范围: 0-100的整数
- 特殊值:
  - 0: 任务开始
  - 100: 任务完成

#### 注意事项
1. AK和SK数量必须相同
2. parallel_num不能大于AK/SK对数量
3. 支持的文件类型: tex, txt, json
4. domain参数用于指定问答对的领域范围，影响生成的问答质量

## 质量控制接口

### 1. 评估和优化问答对
```http
POST /quality
```

**请求参数:**
```json
{
  "content": [                  // 问答对列表,json content, from get content interface
    {
      "question": "string",
      "answer": "string"
    }
  ],
  "filename": "string",         // 文件名， not specified manually
  "model_name": "erine",       // 使用的模型名称
  "domain": "string",          // 领域
  "similarity_rate": 0.3,  // 相似度阈值(0.0-1.0)
  "coverage_rate": 0.5,    // 覆盖率阈值(0.0-1.0)
  "max_attempts": 3,     // 最大优化尝试次数
  "save_path": "result/",       // 保存路径
  "SK": ["4234"],           // Secret Key列表
  "AK": ["str424ing"],           // Access Key列表
  "parallel_num": 1     // 并行处理数量
}
```

**响应:**
```json
{
  "status": "success",
  "message": "QA pairs optimized successfully",
  "data": {
    "optimized_pairs": [
      {
        "question": "string",
        "answer": "string",
        "metrics": {
          "similarity": "number",    // 相似度得分
          "coverage": "number"       // 覆盖率得分
        }
      }
    ],
    "save_path": "string"           // 结果保存路径
  }
}
```

### 2. 获取问答对文件列表
```http
GET /qa_files
```

**响应:**
```json
{
  "status": "success",
  "message": "获取文件列表成功",
  "data": {
    "files": [
      {
        "filename": "string",
        "created_at": "datetime",
        "file_type": "string",
        "size": "number",
        "status": "string"
      }
    ]
  }
}
```

### 3. 获取问答对文件内容
```http
GET /qa_content/{filename}
```

**参数说明:**
- `filename`: 问答对文件名

**响应:**
```json
{
  "status": "success",
  "message": "获取文件内容成功",
  "data": {
    "content": [
      {
        "question": "string",
        "answer": "string"
      }
    ],
    "filename": "string",
    "created_at": "datetime",
    "file_type": "string"
  }
}
```

### 4. 获取质量控制历史记录
```http
GET /quality/history
```

**响应:**
```json
{
  "status": "success",
  "message": "Records retrieved successfully",
  "data": {
    "records": [
      {
        "filename": "string",
        "model_name": "string",
        "domain": "string",
        "similarity_rate": "number",
        "coverage_rate": "number",
        "status": "string",
        "progress": "number",
        "created_at": "datetime",
        "optimized_count": "number",
        "total_count": "number",
        "save_path": "string"
      }
    ]
  }
}
```

### 状态说明

#### 任务状态(status)
- `processing`: 质量评估优化中
- `completed`: 评估优化完成
- `failed`: 评估优化失败

#### 评估指标
1. 相似度(similarity)
   - 范围: 0.0-1.0
   - 推荐阈值: 0.8
   - 说明: 衡量问答对的问题和答案之间的语义相关性

2. 覆盖率(coverage)
   - 范围: 0.0-1.0
   - 推荐阈值: 0.8
   - 说明: 衡量答案对问题要点的覆盖程度

#### 注意事项
1. similarity_rate和coverage_rate用于设置质量控制的标准
2. max_attempts限制单个问答对的优化尝试次数
3. 优化过程会保留原始问答对，方便对比和回溯
4. domain参数影响评估标准的具体实现

## 去重接口(待修改)

### 1. 问答对去重
```http
POST /deduplicate_qa
```

**请求参数:**
```json
{
  "input_file": ["string"],      // 输入文件路径列表
  "dedup_by_answer": "boolean",  // 是否按答案去重
  "min_answer_length": "number", // 最小答案长度
  "dedup_threshold": "number"    // 去重阈值(0.0-1.0)
}
```

**响应:**
```json
{
  "status": "success",
  "message": "QA pairs deduplicated successfully",
  "data": {
    "original_count": "number",  // 原始问答对数量
    "kept_count": "number",      // 保留的问答对数量
    "deleted_pairs": [           // 被删除的问答对
      {
        "question": "string",
        "answer": "string",
        "similar_pairs": [       // 相似的问答对
          {
            "question": "string",
            "answer": "string",
            "similarity": "number"
          }
        ]
      }
    ],
    "save_path": "string"        // 结果保存路径
  }
}
```

### 2. 获取去重历史记录
```http
GET /deduplicate_qa/history
```

**响应:**
```json
{
  "status": "success",
  "message": "Records retrieved successfully",
  "data": {
    "records": [
      {
        "input_file": ["string"],
        "output_file": "string",
        "deleted_pairs_file": "string",
        "dedup_by_answer": "boolean",
        "threshold": "number",
        "min_answer_length": "number",
        "status": "string",
        "original_count": "number",
        "kept_count": "number",
        "progress": "number",
        "created_at": "datetime"
      }
    ]
  }
}
```

### 3. 获取去重进度
```http
GET /dedup/progress/{record_id}
```

**参数说明:**
- `record_id`: 去重任务ID

**响应:**
```json
{
  "status": "success",
  "message": "Progress retrieved successfully",
  "data": {
    "progress": "number",     // 进度百分比(0-100)
    "status": "string"       // 任务状态: processing, completed, failed
  }
}
```

### 状态说明

#### 任务状态(status)
- `processing`: 去重处理中
- `completed`: 去重完成
- `failed`: 去重失败

#### 进度说明(progress)
- 范围: 0-100的整数
- 特殊值:
  - 0: 任务开始
  - 100: 任务完成

#### 相似度阈值(dedup_threshold)
- 范围: 0.0-1.0
- 推荐值: 0.8
- 说明: 
  - 值越大要求问答对越相似才会被判定为重复
  - 值越小去重效果越激进