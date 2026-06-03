import { motion } from 'framer-motion';
import ProgressBar from '../components/ProgressBar';
import { InfoTip } from '../components/InfoTip';

interface Props {
  valueWeight: number;
  valueCap: number;
  growthWeight: number;
  growthCap: number;
}

export function RiskBarWidget({ valueWeight, valueCap, growthWeight, growthCap }: Props) {
  return (
    <div>
      <ProgressBar
        value={valueWeight}
        max={valueCap}
        label={`VALUE 组（白酒+银行+红利+沪深300）`}
        showPercent
        color="auto"
        height={10}
        info={`因子组约束 · 防伪分散\nVALUE组上限=${Math.round(valueCap*100)}%\n超限→组内等比缩减，溢出进国债\n公式：组权重 = Σ 组内各资产权重`}
      />
      <div className="mt-4">
        <ProgressBar
          value={growthWeight}
          max={growthCap}
          label={`GROWTH 组（科创50）`}
          showPercent
          color="auto"
          height={10}
          info={`因子组约束 · 防单一成长\nGROWTH组上限=${Math.round(growthCap*100)}%\n超限→缩减，溢出进国债`}
        />
      </div>
      <div className="text-xs text-[#9CA3AF] mt-3 flex items-center gap-1">
        {valueWeight === 0 && growthWeight === 0
          ? '初始建仓模式：当前持仓为零，因子组约束在后续月份生效'
          : '绿色=安全 | 黄色=接近上限 | 红色=触及上限'}
        <InfoTip text={`单资产约束：\n权重 < 上限−5% → 系数1\n上限−5% ≤ 权重 < 上限 → (上限−权重)/5%\n权重 ≥ 上限 → 系数0`} />
      </div>
    </div>
  );
}
