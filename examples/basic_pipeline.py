from stagewatch import Pipeline, stage

pipeline = Pipeline("sample-etl")
pipeline.expect_range("normalize", minimum=0.0, maximum=1.0)


@stage(pipeline)
def load(_seed):
    return [0.2, 0.4, 0.6, 0.8]


@stage(pipeline)
def normalize(values):
    return [value / max(values) for value in values]


@stage(pipeline)
def summarize(values):
    return {"count": len(values), "mean": sum(values) / len(values)}


result = pipeline.run("demo-seed", metadata={"environment": "example"})
print("Result:", result)
print(pipeline.report())
print("HTML:", pipeline.report(format="html"))
