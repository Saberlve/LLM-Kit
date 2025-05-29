# 修复LaTeX转换进度查询接口问题

## 问题描述

后端日志显示找不到`/to_tex/progress`接口，这是因为在路由注册和路由定义中存在路径不匹配的问题。

## 修复方法

### 1. 修改后端路由路径

在`app/components/routers/to_tex.py`文件中，将：

```python
@router.post("/to_tex/progress")
```

修改为：

```python
@router.post("/progress")
```

这样做的原因是路由前缀`/to_tex`已经在`main.py`中注册了：

```python
app.include_router(to_tex.router, prefix="/to_tex", tags=["to_tex"])
```

### 2. 同时修改前端调用代码

在`frontend/src/routes/construct/+page.svelte`文件中，找到以下代码：

```javascript
const response = await axios.post('http://127.0.0.1:8000/to_tex/progress', {
    filename: filename
});
```

保持不变，因为前端需要完整的URL路径(`/to_tex/progress`)，它与后端路由的组合(`/to_tex` + `/progress`)匹配。

## 验证

修改完成后，LaTeX转换进度查询接口应该可以正常工作，不再出现404错误。 